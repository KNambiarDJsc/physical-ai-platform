"""RI-008: reproducible JSON report and an HTML report rendered from it only, on a real engine run."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from helpers import as_user, ok
from test_jobs import P, submit, work_once

pytestmark = pytest.mark.engine


def _sha(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


@pytest.fixture
def finished(client: TestClient, demo: dict[str, Any], omhs: Any) -> str:
    job = submit(client, demo["body"])
    r = client.get(f"{P}/evaluations/{job['id']}/report.json", headers=as_user("alice"))
    assert r.status_code == 409  # no report before the evaluation succeeded
    assert work_once() == "succeeded"
    return str(job["id"])


def test_json_report_is_reproducible_and_complete(client: TestClient, finished: str, demo: dict[str, Any]) -> None:
    h = as_user("alice")
    url = f"{P}/evaluations/{finished}/report.json"
    first, second = client.get(url, headers=h), client.get(url, headers=h)
    assert first.status_code == 200 and first.headers["content-type"].startswith("application/json")
    assert first.content == second.content, "the same evaluation must give byte-identical reports"
    assert first.headers["x-report-sha256"] == _sha(first.content)
    assert "attachment" in first.headers["content-disposition"]

    # Regenerated from the database in a fresh session, not cached
    from app.db import session_factory
    from app.evaluations import reports
    from app.evaluations.models import EvaluationJob

    with session_factory()() as s:
        job = s.get(EvaluationJob, __import__("uuid").UUID(finished))
        assert job is not None
        assert reports.serialize(reports.build_report(s, job)) == first.content

    rep = json.loads(first.content)
    ev = ok(client.get(f"{P}/evaluations/{finished}", headers=h))
    cmp_ = ok(client.get(f"{P}/evaluations/{finished}/comparison", headers=h))
    mapping = ok(client.get(f"{P}/mappings/{demo['mapping']}", headers=h))

    assert rep["schema"] == "pap.report/1"
    assert rep["evidence_class"] == ["synthetic"]
    assert rep["evaluation"]["input_sha256"] == ev["input_sha256"]
    assert rep["provenance"] == ev["provenance"]
    assert rep["provenance"]["engine"]["commit"] == "e9ef873b42f74f201aecf392ee6e61453e1f40a4"
    assert rep["mapping"]["spec_sha256"] == mapping["spec_sha256"]
    assert rep["mapping"]["version"] == mapping["version"]
    assert {i["sha256"] for i in rep["inputs"]} == {s for v in ev["provenance"]["inputs"].values() for s in v}, (
        "every input checksum is in the report"
    )
    outs = rep["engine_outputs"]
    assert {"compare_reported", "compare_verified", "compare_paired", "incidents", "validation"} <= set(outs)
    for kind, o in outs.items():
        assert o["raw_sha256"] == _sha(o["raw"].encode("utf-8")), kind
    for kind, key in (("compare_reported", "reported"), ("compare_verified", "verified"), ("compare_paired", "paired")):
        assert outs[kind]["raw"] == cmp_[key]["raw"], "engine output embedded byte for byte"
    assert json.loads(outs["compare_reported"]["raw"])["verdict"] == ev["summary"]["verdict_reported"]
    assert json.loads(outs["compare_verified"]["raw"])["verdict"] == ev["summary"]["verdict_verified"]
    assert len(rep["episodes"]) == ev["summary"]["episodes"] == 240
    assert rep["episodes"] == sorted(rep["episodes"], key=lambda e: (e["release"], e["ended_at"], e["episode_key"]))
    assert "generated_at" not in first.text  # nothing time-of-generation dependent


def test_html_report_is_rendered_from_the_json_only(client: TestClient, finished: str) -> None:
    from app.evaluations.reports import render_html

    h = as_user("alice")
    data = client.get(f"{P}/evaluations/{finished}/report.json", headers=h).content
    page = client.get(f"{P}/evaluations/{finished}/report.html", headers=h)
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert page.content == client.get(f"{P}/evaluations/{finished}/report.html", headers=h).content
    # The HTML is exactly what the pure renderer makes from the JSON report: no other input
    assert page.text == render_html(json.loads(data))
    assert f'name="pap-report-sha256" content="{_sha(data)}"' in page.text
    assert page.headers["x-report-sha256"] == _sha(data)
    assert "default-src 'none'" in page.headers["content-security-policy"]

    text = page.text
    if os.environ.get("PAP_WRITE_REPORT_SAMPLE"):  # for visual review only; var/ is not committed
        out = Path(__file__).resolve().parents[3] / "var" / "report-sample"
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_bytes(data)
        (out / "report.html").write_bytes(page.content)
    assert "SYNTHETIC EVIDENCE" in text and "says nothing about the performance of any real system" in text
    assert "Improvement" in text and "Insufficient evidence" in text  # reported vs verified, as the engine said
    assert "e9ef873b42f74f201aecf392ee6e61453e1f40a4" in text
    rep = json.loads(data)
    for i in rep["inputs"]:
        assert i["sha256"] in text
    assert rep["mapping"]["spec_sha256"] in text
    n_attention = sum(e["outcome_class"] in ("contradiction", "unknown") for e in rep["episodes"])
    assert f"Contradictions and unknowns ({n_attention})" in text and n_attention > 0
    # Self-contained: no script, no external resource
    assert "<script" not in text.lower()
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", text, re.I)


def test_html_escapes_and_states_every_evidence_class(client: TestClient, finished: str) -> None:
    from app.evaluations.reports import render_html

    rep = json.loads(client.get(f"{P}/evaluations/{finished}/report.json", headers=as_user("alice")).content)
    hostile = copy.deepcopy(rep)
    hostile["releases"]["candidate"]["label"] = "<script>alert(1)</script>"
    hostile["episodes"][0].update(outcome_class="contradiction", robot='"><img src=x onerror=alert(1)>')
    out = render_html(hostile)
    assert "<script>alert(1)" not in out and "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "<img src=x" not in out
    for cls, phrase in (("simulated", "SIMULATED EVIDENCE"), ("production", "PRODUCTION EVIDENCE")):
        r = copy.deepcopy(rep)
        r["evidence_class"] = [cls]
        assert phrase in render_html(r)
        assert "SYNTHETIC EVIDENCE" not in render_html(r)
    with pytest.raises(ValueError):
        render_html({**rep, "schema": "something/else"})


def test_report_requires_access(client: TestClient, finished: str) -> None:
    for fmt in ("json", "html"):
        r = client.get(f"{P}/evaluations/{finished}/report.{fmt}", headers=as_user("mallory"))
        assert r.status_code == 404 and finished not in r.text
