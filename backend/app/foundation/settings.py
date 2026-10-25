"""Explicit settings: never load dotenv or legacy configuration."""
from dataclasses import dataclass, field
from typing import Mapping
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

class FoundationConfigurationError(ValueError):
    pass

def postgres_url(value: str, name: str) -> URL:
    try:
        url = make_url(value)
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        if (url.drivername != "postgresql+psycopg" or not url.host or not url.database
                or not url.username or not url.password or set(url.query) - {"sslmode"}
                or (url.port is not None and not 1 <= url.port <= 65535)):
            raise ValueError
        if "sslmode" in url.query and url.query["sslmode"] not in {
            "disable", "allow", "prefer", "require", "verify-ca", "verify-full"
        }:
            raise ValueError
        return url
    except (ValueError, TypeError, ArgumentError):
        raise FoundationConfigurationError(f"{name} must be an explicit PostgreSQL URL.") from None

@dataclass(frozen=True)
class FoundationSettings:
    enabled: bool = False
    application_database_url: URL | None = field(default=None, repr=False)
    pool_size: int = 2
    max_overflow: int = 0
    pool_timeout: int = 5
    connect_timeout: int = 5
    statement_timeout_ms: int = 5000
    lock_timeout_ms: int = 2000
    idle_transaction_timeout_ms: int = 10000

    def __post_init__(self):
        limits = {"pool_size": (1, 10), "max_overflow": (0, 5), "pool_timeout": (1, 30),
                  "connect_timeout": (1, 15), "statement_timeout_ms": (100, 60000),
                  "lock_timeout_ms": (100, 10000), "idle_transaction_timeout_ms": (1000, 60000)}
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise FoundationConfigurationError(f"{name} is outside its bounded range.")
        if self.enabled:
            if not isinstance(self.application_database_url, URL):
                raise FoundationConfigurationError("WPL_APPLICATION_DATABASE_URL is required.")
            postgres_url(self.application_database_url.render_as_string(hide_password=False), "WPL_APPLICATION_DATABASE_URL")

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]):
        flag = values.get("WPL_FOUNDATION_ENABLED", "false").lower()
        if flag not in {"true", "false"}:
            raise FoundationConfigurationError("WPL_FOUNDATION_ENABLED must be true or false.")
        if flag == "false":
            return cls()
        return cls(enabled=True, application_database_url=postgres_url(
            values.get("WPL_APPLICATION_DATABASE_URL", ""), "WPL_APPLICATION_DATABASE_URL"))
