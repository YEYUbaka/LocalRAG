from pathlib import Path

from scripts.check_clean_baseline import check_manifest


def test_manifest_reports_missing_and_forbidden_files(tmp_path: Path):
    (tmp_path / "tracked.txt").write_text("ok", encoding="utf-8")
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("tracked.txt\nmissing.txt\n", encoding="utf-8")

    result = check_manifest(
        root=tmp_path,
        manifest_path=manifest,
        tracked_paths={"tracked.txt", ".env"},
    )

    assert result.missing == ("missing.txt",)
    assert result.forbidden_tracked == (".env",)
    assert result.ok is False
