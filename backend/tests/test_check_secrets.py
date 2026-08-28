"""Regression coverage for backend/scripts/check_secrets.py rules.

Positive-case payloads are built via concatenation so this file itself never
matches the scanner rules it exercises.
"""

from backend.scripts.check_secrets import RULES

_REAL_PW = "db-pass" + "-123"


def _hit(rule_id: str, text: str) -> bool:
    return RULES[rule_id].search(text) is not None


def test_db_url_rule_flags_real_looking_password():
    assert _hit("db_url_credentials", "mysql+pymysql://root:" + _REAL_PW + "@localhost:3306/localrag")
    assert _hit("db_url_credentials", "postgresql://app:" + _REAL_PW + "@db.internal:5432/prod")
    assert _hit("db_url_credentials", "https://ci:" + _REAL_PW + "@github.example/x/y.git")


def test_db_url_rule_allows_documented_placeholders():
    for url in (
        "mysql+pymysql://root:localrag@mysql:3306/localrag",
        "mysql+pymysql://root:root@127.0.0.1:3306/localrag_test",
        "mysql+pymysql://root:password@localhost:3306/localrag",
        "mysql+pymysql://root:your-password@localhost:3306/localrag",
        "mysql+pymysql://root:changeme@localhost:3306/localrag",
    ):
        assert not _hit("db_url_credentials", url), url


def test_db_url_rule_ignores_credentialless_urls():
    assert not _hit("db_url_credentials", "mysql+pymysql://localhost:3306/localrag")
    assert not _hit("db_url_credentials", "see https://example.com/docs for details")


def test_existing_assignment_rules_still_fire():
    assert _hit("jwt_secret_assignment", "JWT_" + "SECRET=too-short-but-real")
    assert not _hit("jwt_secret_assignment", "JWT_" + "SECRET=your-secret-here")
    assert _hit("llm_api_key_assignment", "LLM_" + "API_KEY=sk-live-abc")
    assert not _hit("llm_api_key_assignment", "LLM_" + "API_KEY=sk-your-key-here")
