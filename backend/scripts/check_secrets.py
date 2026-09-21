"""Local secret scanner for tracked files.

Reads tracked text files only (git ls-files), skips contract snapshots and
lock-file integrity strings, and rejects private key headers, JWT-looking
values, OpenAI-style keys, assignments of JWT_SECRET/LLM_API_KEY to
non-example values, and database URLs carrying non-placeholder passwords.
Prints path, line number and rule ID — never the value.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

# Rule ID -> compiled regex. Rules must never capture the matched value.
RULES: dict[str, re.Pattern[str]] = {
    "private_key_header": re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    "jwt_like": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "jwt_secret_assignment": re.compile(r"^\s*JWT_SECRET\s*=\s*(?!your-)[^\s#]+", re.MULTILINE),
    "llm_api_key_assignment": re.compile(r"^\s*LLM_API_KEY\s*=\s*(?!sk-your)[^\s#]+", re.MULTILINE),
    # URL with embedded user and password, where the password is not one of
    # the documented placeholder values (container-internal and doc-example
    # credentials are allowed). Scheme must start with a letter so this
    # rule's own source text cannot self-match.
    "db_url_credentials": re.compile(
        r"\b[a-zA-Z][\w+.-]*://[^\s/:@]+:(?!localrag\b|root\b|password\b|your-password\b|changeme\b)[^\s/@]+@"
    ),
}

# Paths where rule hits are expected/benign (templates, snapshots, lockfiles)
_SKIP_SUFFIXES = (".lock", ".json", ".example")
_SKIP_PARTS = ("contracts",)


def scan_tracked(root: Path) -> list[tuple[str, int, str]]:
    """Return [(path, line_number, rule_id)] for tracked files."""
    output = subprocess.check_output(
        ["git", "-C", str(root), "ls-files"], text=True, encoding="utf-8"
    )
    findings: list[tuple[str, int, str]] = []
    for rel in output.splitlines():
        if not rel:
            continue
        path = root / rel
        if path.suffix in _SKIP_SUFFIXES or any(part in _SKIP_PARTS for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        # Only scan text files
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for rule_id, pattern in RULES.items():
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append((str(rel), line_no, rule_id))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    findings = scan_tracked(args.root)
    for path, line, rule in findings:
        print(f"{path}:{line} [{rule}]")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
