import os
from dataclasses import dataclass
from typing import Protocol


class SecretProvider(Protocol):
    def get(self, name: str) -> str | None: ...


class EnvironmentSecretProvider:
    def get(self, name: str) -> str | None:
        value = os.environ.get(name)
        return value if value else None


def require_secret(provider: SecretProvider, name: str, minimum_bytes: int = 32) -> str:
    value = provider.get(name)
    if value is None or len(value.encode("utf-8")) < minimum_bytes:
        raise RuntimeError(f"{name} must contain at least {minimum_bytes} UTF-8 bytes")
    return value


@dataclass(frozen=True, slots=True)
class AuthConfig:
    secret: str
    issuer: str
    audience: str
    access_token_minutes: int


def build_auth_config(provider: SecretProvider) -> AuthConfig:
    return AuthConfig(
        secret=require_secret(provider, "JWT_SECRET"),
        issuer="localrag",
        audience="localrag-api",
        access_token_minutes=30,
    )
