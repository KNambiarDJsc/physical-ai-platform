"""``outcome.verified.conditions`` from a verifier report (RFC 0005 §1.1, ADR-0035 in OpenMHS).

Copied from OpenMHS ``python/openmhs/importers/coresense_verify.py::conditions_of`` at commit
e9ef873b42f74f201aecf392ee6e61453e1f40a4 (Copyright OpenMHS contributors, Apache License 2.0). It is not a public
OpenMHS API (gap G-2 in docs/engine-contract-gaps.md). A parity test runs both on real reports when the pinned
source tree is present, and the engine refuses conditions that contradict the verdict.

Each condition as the verifier judged it: the bounds from the contract, the result and the values of the records
the verifier used, copied, never recomputed.
"""

from __future__ import annotations

from typing import Any


def conditions_of(contract_obj: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for cr in report["conditions"]:
        planned = contract_obj["conditions"][cr["index"]]
        c = {"evidence": cr["evidence"], "op": cr["op"], "result": cr["result"].lower(), "observed": cr["observed"]}
        if cr.get("name"):
            c["name"] = cr["name"]
        for k in ("min", "max", "value", "values"):
            if k in planned:
                c[k] = planned[k]
        out.append(c)
    return out
