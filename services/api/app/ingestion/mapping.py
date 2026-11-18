"""Apply a ``pap.mapping/1`` to the bytes of one source artifact.

Invariant: every data row ends up as exactly one episode or one rejection (with its row number and reason).
Artifact-level problems (encoding, header, too many rows, broken CSV quoting) reject the artifact as a whole rather
than a guessed subset. Values are never invented: a missing optional field is recorded as unavailable.

This module also builds the RFC 0004 verifier input for an episode (``verifier_input``). It does not judge
anything; ``openmhs outcome verify`` does.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..contracts.episode import Episode, EpisodeContext, Field_, SourceLocator
from ..contracts.mapping import MappingSpec, Measurement, Source, TimeSource

MAX_CELL = 64 * 1024
MAX_LINE = 1024 * 1024
TRUE = {"true", "1", "yes", "y", "t"}
FALSE = {"false", "0", "no", "n", "f"}


class ArtifactRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class RowRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Rejection:
    row: int
    code: str
    message: str


@dataclass(frozen=True)
class MeasuredValue:
    name: str
    value: Any
    time: str | None
    clock_domain: str | None
    uncertainty_ms: float | None
    quality: str | None


@dataclass(frozen=True)
class MappedEpisode:
    episode: Episode
    measured: tuple[MeasuredValue, ...]
    ended_uncertainty_ms: float | None


@dataclass
class MappingResult:
    rows: int = 0
    episodes: list[MappedEpisode] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    unavailable: dict[str, int] = field(default_factory=dict)

    def report(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "episodes": len(self.episodes),
            "rejected": len(self.rejections),
            "rejections": [r.__dict__ for r in self.rejections[:1000]],
            "rejections_truncated": max(0, len(self.rejections) - 1000),
            "unavailable": dict(sorted(self.unavailable.items())),
        }


# ------------------------------------------------------------------------------------------------ reading rows


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ArtifactRejected("input.encoding", f"not UTF-8 at byte {e.start}") from e


def _rows_csv(text: str, spec: MappingSpec) -> Iterator[tuple[int, dict[str, Any] | RowRejected]]:
    if "\x00" in text:
        raise ArtifactRejected("input.nul", "the file contains NUL bytes")
    csv.field_size_limit(MAX_CELL)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=spec.input.delimiter, strict=True)
    try:
        header = next(reader)
    except StopIteration as e:
        raise ArtifactRejected("input.empty", "no header row") from e
    except csv.Error as e:
        raise ArtifactRejected("input.csv", f"header: {e}") from e
    header = [h.strip() for h in header]
    if len(set(header)) != len(header) or any(not h for h in header):
        raise ArtifactRejected("input.header", "header has empty or duplicate column names")
    n = 0
    while True:
        try:
            cells = next(reader)
        except StopIteration:
            return
        except csv.Error as e:
            raise ArtifactRejected("input.csv", f"data row {n + 1}: {e}") from e
        if not cells or all(not c.strip() for c in cells):
            continue  # blank line: not a row
        n += 1
        if len(cells) != len(header):
            yield n, RowRejected("row.columns", f"{len(cells)} cells, header has {len(header)}")
        else:
            yield n, dict(zip(header, cells, strict=True))


def _rows_jsonl(text: str) -> Iterator[tuple[int, dict[str, Any] | RowRejected]]:
    n = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        n += 1
        if len(line) > MAX_LINE:
            yield n, RowRejected("row.too_large", f"line longer than {MAX_LINE} characters")
            continue
        try:
            obj = json.loads(line)
        except (ValueError, RecursionError) as e:
            yield n, RowRejected("row.json", f"invalid JSON: {str(e)[:200]}")
            continue
        if not isinstance(obj, dict):
            yield n, RowRejected("row.json", "line is not a JSON object")
        else:
            yield n, obj


# ------------------------------------------------------------------------------------------------ values


def _cell(row: dict[str, Any], column: str) -> str | None:
    cur: Any = row
    if column in row:
        cur = row[column]
    else:
        for part in column.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
    if cur is None:
        return None
    if isinstance(cur, bool):
        return "true" if cur else "false"
    if isinstance(cur, int | float):
        if isinstance(cur, float) and not math.isfinite(cur):
            raise RowRejected("row.value", f"{column}: non-finite number")
        return json.dumps(cur)
    if isinstance(cur, str):
        s = cur.strip()
        if len(s) > MAX_CELL:
            raise RowRejected("row.value", f"{column}: value too long")
        return s or None
    raise RowRejected("row.value", f"{column}: expected a scalar, got {type(cur).__name__}")


def _get(row: dict[str, Any], src: Source | None) -> str | None:
    if src is None:
        return None
    return src.const if src.const is not None else _cell(row, src.column or "")


def _time(row: dict[str, Any], src: TimeSource, what: str) -> str | None:
    raw = _get(row, src)
    if raw is None:
        return None
    try:
        if src.format == "rfc3339":
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                raise RowRejected("row.time", f"{what}: {raw!r} has no UTC offset; times are never assumed to be UTC")
        else:
            x = float(raw)
            if not math.isfinite(x):
                raise ValueError(raw)
            dt = datetime.fromtimestamp(x / 1000 if src.format == "unix_ms" else x, tz=UTC)
    except (ValueError, OverflowError, OSError) as e:
        raise RowRejected("row.time", f"{what}: cannot read {raw!r} as {src.format}") from e
    return dt.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _measured(row: dict[str, Any], m: Measurement, spec: MappingSpec) -> MeasuredValue | None:
    raw = _cell(row, m.column)
    if raw is None:
        if spec.missing_data.measurement == "reject":
            raise RowRejected("row.measurement_missing", f"{m.column} is blank")
        return None
    value: Any
    if m.value_type == "number":
        try:
            value = float(raw)
        except ValueError as e:
            raise RowRejected("row.measurement", f"{m.column}: {raw!r} is not a number") from e
        if not math.isfinite(value):
            raise RowRejected("row.measurement", f"{m.column}: non-finite")
        if value.is_integer() and abs(value) < 2**53:
            value = int(value)
        if m.unit:
            value = {"value": value, "unit": m.unit}
    elif m.value_type == "boolean":
        low = raw.lower()
        if low not in TRUE | FALSE:
            raise RowRejected("row.measurement", f"{m.column}: {raw!r} is not a boolean")
        value = low in TRUE
    else:
        value = raw
    quality = None
    if m.quality_column:
        quality = _cell(row, m.quality_column)
        if quality is not None and quality.upper() not in ("GOOD", "UNCERTAIN", "BAD"):
            raise RowRejected("row.quality", f"{m.quality_column}: {quality!r} is not GOOD, UNCERTAIN or BAD")
        quality = quality.upper() if quality else None
    t = _time(row, m.time, f"{m.name} time") if m.time else None
    return MeasuredValue(
        name=m.name,
        value=value,
        time=t,
        clock_domain=m.time.clock_domain if m.time else None,
        uncertainty_ms=m.time.uncertainty_ms if m.time else None,
        quality=quality,
    )


# ------------------------------------------------------------------------------------------------ mapping


def apply_mapping(
    spec: MappingSpec,
    data: bytes,
    *,
    artifact_sha256: str,
    release: str,
    mapping_ref: str,
    context: EpisodeContext,
) -> MappingResult:
    text = _decode(data)
    rows = _rows_csv(text, spec) if spec.input.format == "csv" else _rows_jsonl(text)
    result = MappingResult()
    seen: dict[str, int] = {}

    def unavailable(name: str) -> Field_:
        result.unavailable[name] = result.unavailable.get(name, 0) + 1
        return Field_(available=False, value=None)

    for n, row in rows:
        result.rows = n
        if n > spec.input.max_rows:
            raise ArtifactRejected("input.too_many_rows", f"more than {spec.input.max_rows} rows")
        try:
            if isinstance(row, RowRejected):
                raise row
            key = _get(row, spec.episode_id)
            robot = _get(row, spec.robot)
            task_type = _get(row, spec.task_type)
            for name, v in (("episode_id", key), ("robot", robot), ("task_type", task_type)):
                if v is None:
                    raise RowRejected("row.required", f"{name} is missing")
            assert key is not None and robot is not None and task_type is not None
            if key in seen:
                raise RowRejected("row.duplicate", f"episode {key!r} already read at row {seen[key]}")
            fields: dict[str, Field_] = {}
            for name, src in (("site", spec.site), ("scenario", spec.scenario)):
                v = _get(row, src)
                if v is None and getattr(spec.missing_data, name) == "reject":
                    raise RowRejected("row.required", f"{name} is missing")
                fields[name] = Field_(available=True, value=v) if v is not None else unavailable(name)
            started = _time(row, spec.started_at, "started_at") if spec.started_at else None
            if started is None and spec.missing_data.started_at == "reject":
                raise RowRejected("row.required", "started_at is missing")
            ended = _time(row, spec.ended_at, "ended_at")
            if ended is None:
                raise RowRejected("row.required", "ended_at is missing")
            raw_reported = _cell(row, spec.reported_outcome.column)
            if raw_reported is None:
                if spec.reported_outcome.missing == "reject":
                    raise RowRejected("row.required", "reported outcome is missing")
                reported = "unknown"
                unavailable("reported_outcome")
            elif raw_reported in spec.reported_outcome.values:
                reported = spec.reported_outcome.values[raw_reported]
            else:
                raise RowRejected("row.reported", f"reported value {raw_reported!r} is not in the mapping")
            measured = tuple(mv for m in spec.measurements if (mv := _measured(row, m, spec)) is not None)
            for m in spec.measurements:
                if m.name not in {mv.name for mv in measured}:
                    result.unavailable[f"measurement.{m.name}"] = result.unavailable.get(f"measurement.{m.name}", 0) + 1
            raw_cells = {m.name: _cell(row, m.column) for m in spec.measurements}
            ep = Episode(
                organization=context.organization,
                project=context.project,
                evaluation=context.evaluation,
                episode_key=key,
                release=release,
                robot=robot,
                task_type=task_type,
                site=fields["site"],
                scenario=fields["scenario"],
                started_at=Field_(available=True, value=started) if started else unavailable("started_at"),
                ended_at=ended,
                clock_domain=spec.ended_at.clock_domain,
                reported=reported,
                reported_raw=raw_reported,
                measurements=raw_cells,
                source=SourceLocator(artifact_sha256=artifact_sha256, row=n),
                mapping=mapping_ref,
                evidence_class=spec.evidence_class,
            )
            seen[key] = n
            result.episodes.append(MappedEpisode(ep, measured, spec.ended_at.uncertainty_ms))
        except RowRejected as r:
            result.rejections.append(Rejection(row=n, code=r.code, message=r.message))
    assert result.rows == len(result.episodes) + len(result.rejections), "a row was lost"
    return result


# ------------------------------------------------------------------------------------------------ RFC 0004 input

ANCHOR = "claim"


def verifier_input(spec: MappingSpec, me: MappedEpisode) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """The contract (bound to this episode, anchored on the robot's report) and the evidence records.

    None when the mapping declares no contract. A measurement whose cell was blank produces no record: the
    verifier then reports ``evidence.missing`` for it, which is the honest answer.
    """
    if spec.contract is None:
        return None
    ep = me.episode
    provenance = "device" if spec.evidence_class == "production" else "simulator"
    items: dict[str, Any] = {ANCHOR: {"signal": "task.reported", "kind": "controller"}}
    by_name = {m.name: m for m in spec.measurements}
    for m in spec.measurements:
        item: dict[str, Any] = {"signal": m.signal, "kind": m.kind}
        if m.device:
            item["device"] = m.device
        items[m.name] = item
    conditions = []
    for c in spec.contract.conditions:
        cond: dict[str, Any] = {"name": c.name, "evidence": c.evidence, "op": c.op}
        for k in ("value", "values", "min", "max"):
            v = getattr(c, k)
            if v is not None:
                cond[k] = v
        conditions.append(cond)
    contract = {
        "contract": spec.contract.name,
        "version": spec.contract.version,
        "binding": {"episode": ep.episode_key},
        "timing": {
            "anchor": ANCHOR,
            "default_window_ms": list(spec.contract.window_ms),
            "max_clock_uncertainty_ms": spec.contract.max_clock_uncertainty_ms,
        },
        "evidence": items,
        "conditions": conditions,
    }
    anchor_time: dict[str, Any] = {"source": ep.ended_at, "clock_domain": ep.clock_domain}
    if me.ended_uncertainty_ms is not None:
        anchor_time["uncertainty_ms"] = me.ended_uncertainty_ms
    records: list[dict[str, Any]] = [
        {
            "id": ANCHOR,
            "signal": "task.reported",
            "value": ep.reported,
            "source": {"system": spec.name, "kind": "controller", "provenance": provenance},
            "time": anchor_time,
            "refs": {"episode": ep.episode_key},
        }
    ]
    for mv in me.measured:
        m = by_name[mv.name]
        src: dict[str, Any] = {"system": m.system, "kind": m.kind, "provenance": provenance}
        if m.device:
            src["device"] = m.device
        rec: dict[str, Any] = {
            "id": mv.name,
            "signal": m.signal,
            "value": mv.value,
            "source": src,
            "refs": {"episode": ep.episode_key},
        }
        if mv.time is not None:
            t: dict[str, Any] = {"source": mv.time, "clock_domain": mv.clock_domain}
            if mv.uncertainty_ms is not None:
                t["uncertainty_ms"] = mv.uncertainty_ms
            rec["time"] = t
        if mv.quality is not None:
            rec["quality"] = mv.quality
        records.append(rec)
    return contract, records
