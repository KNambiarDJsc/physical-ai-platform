"""Write (or check) the JSON Schemas of the platform's versioned documents into packages/contracts/schema.

python -m app.contracts.export          # write
python -m app.contracts.export --check  # exit 1 when the committed schemas differ from the models
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from .episode import CONFIG_SCHEMA, EPISODE_SCHEMA, Episode, EvaluationConfig
from .mapping import SCHEMA as MAPPING_SCHEMA
from .mapping import MappingSpec

OUT = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "schema"
DOCUMENTS: dict[str, type[BaseModel]] = {
    MAPPING_SCHEMA: MappingSpec,
    EPISODE_SCHEMA: Episode,
    CONFIG_SCHEMA: EvaluationConfig,
}


def render() -> dict[str, str]:
    out = {}
    for name, model in DOCUMENTS.items():
        schema = model.model_json_schema(by_alias=True)
        schema["$id"] = f"https://schemas.physical-ai-platform.dev/{name}.json"
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        out[name.replace("/", "-") + ".schema.json"] = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    return out


def main() -> int:
    files = render()
    if "--check" in sys.argv:
        stale = [n for n, text in files.items() if not (OUT / n).exists() or (OUT / n).read_text("utf-8") != text]
        for n in stale:
            print(f"schema out of date: {n} (run python -m app.contracts.export)", file=sys.stderr)
        return 1 if stale else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for n, text in files.items():
        (OUT / n).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT / n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
