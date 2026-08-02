from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_TRACKED = frozenset({".env", ".env.local", ".vs", "data"})


@dataclass(frozen=True)
class BaselineResult:
    missing: tuple[str, ...]
    forbidden_tracked: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.forbidden_tracked


def check_manifest(
    root: Path, manifest_path: Path, tracked_paths: set[str]
) -> BaselineResult:
    expected = tuple(
        line.strip().replace("\\", "/")
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
    normalized = {path.replace("\\", "/") for path in tracked_paths}
    missing = tuple(path for path in expected if not (root / path).exists())
    forbidden = tuple(
        sorted(
            path for path in normalized
            if path in FORBIDDEN_TRACKED
            or any(path.startswith(f"{prefix}/") for prefix in FORBIDDEN_TRACKED)
        )
    )
    return BaselineResult(missing=missing, forbidden_tracked=forbidden)


def _tracked(root: Path) -> set[str]:
    output = subprocess.check_output(
        ["git", "-C", str(root), "ls-files"], text=True, encoding="utf-8"
    )
    return {line for line in output.splitlines() if line}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = check_manifest(args.root, args.manifest, _tracked(args.root))
    for path in result.missing:
        print(f"missing: {path}")
    for path in result.forbidden_tracked:
        print(f"forbidden-tracked: {path}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
