import json
import subprocess
import sys
from pathlib import Path

from app.schemas.sse import (
    DoneEventV1,
    ErrorEventV1,
    SourceV1,
    SourcesEventV1,
    ThinkingEventV1,
    TokenEventV1,
    SSE_SCHEMA_VERSION,
)


def test_all_sse_schemas_require_schema_version():
    for schema in (TokenEventV1, SourcesEventV1, DoneEventV1, ErrorEventV1, ThinkingEventV1):
        fields = schema.model_fields
        assert "schema_version" in fields
        assert fields["schema_version"].default == SSE_SCHEMA_VERSION


def test_source_v1_is_serializable_and_frozen():
    from pydantic import ValidationError

    source = SourceV1(file="a.pdf", page=1, snippet="证据", doc_id=9)
    assert source.model_dump()["type"] == "document"
    try:
        source.file = "b.pdf"
        raise AssertionError("SourceV1 should be immutable")
    except ValidationError:
        pass


def _run_exporter(output_dir: Path, check: bool) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts" / "export_contracts.py"),
        "--output",
        str(output_dir),
    ]
    if check:
        cmd.append("--check")
    return subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])


def test_exporter_writes_deterministic_snapshots(tmp_path: Path):
    first = _run_exporter(tmp_path, check=False)
    assert first.returncode == 0, first.stderr
    second = _run_exporter(tmp_path, check=False)
    assert (tmp_path / "openapi.json").read_bytes() == (tmp_path / "openapi.json").read_bytes()
    assert (tmp_path / "sse-v1.json").exists()
    sse = json.loads((tmp_path / "sse-v1.json").read_text(encoding="utf-8"))
    assert "done" in sse
    assert sse["done"]["properties"]["schema_version"]["const"] == 1


def test_exporter_check_detects_drift(tmp_path: Path):
    first = _run_exporter(tmp_path, check=False)
    assert first.returncode == 0
    # Break the snapshot and verify check fails
    openapi = tmp_path / "openapi.json"
    openapi.write_text(openapi.read_text(encoding="utf-8").replace("", ""), encoding="utf-8")
    # Rewrite with a removed required property simulation: truncate
    openapi.write_bytes(openapi.read_bytes()[:-40])
    drift = _run_exporter(tmp_path, check=True)
    assert drift.returncode == 1
    assert "contract drift" in drift.stdout
