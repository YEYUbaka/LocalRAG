"""Deterministic OpenAPI/SSE contract exporter.

Normal usage (write snapshots):
    python backend/scripts/export_contracts.py --output backend/contracts

Check mode (fail on drift, no writes):
    python backend/scripts/export_contracts.py --output backend/contracts --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402
from app.schemas.sse import (  # noqa: E402
    DoneEventV1,
    ErrorEventV1,
    SourceV1,
    SourcesEventV1,
    ThinkingEventV1,
    TokenEventV1,
)

SSE_SCHEMAS = {
    "source": SourceV1,
    "token": TokenEventV1,
    "sources": SourcesEventV1,
    "done": DoneEventV1,
    "error": ErrorEventV1,
    "thinking": ThinkingEventV1,
}


def serialize_openapi() -> bytes:
    data = json.loads(json.dumps(app.openapi(), sort_keys=True))
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def serialize_sse() -> bytes:
    defs = {
        name: schema.model_json_schema()
        for name, schema in SSE_SCHEMAS.items()
    }
    return json.dumps(defs, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _write_if_changed(path: Path, content: bytes, check: bool) -> bool:
    existing = path.read_bytes() if path.exists() else None
    normalized = content.rstrip(b"\n") + b"\n"
    if check:
        if existing != normalized:
            print(f"contract drift: {path}")
            return False
        return True
    path.write_bytes(normalized)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    ok = True
    ok &= _write_if_changed(args.output / "openapi.json", serialize_openapi(), args.check)
    ok &= _write_if_changed(args.output / "sse-v1.json", serialize_sse(), args.check)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
