"""Load and validate config from environment variables.

All config comes from env vars. There are no config files and no state files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

DEFAULT_TARGET_SERVICE = "http://localhost:8180"
DEFAULT_POLL_INTERVAL = 120

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class ConfigError(Exception):
    """Raised when a required env var is missing or has a bad value."""


@dataclass(frozen=True)
class Config:
    """Everything the tool needs to run, parsed from env vars."""

    coolify_url: str
    coolify_token: str
    cf_api_token: str
    cf_account_id: str
    cf_tunnel_id: str
    target_service: str = DEFAULT_TARGET_SERVICE
    poll_interval: int = DEFAULT_POLL_INTERVAL
    sync_dns: bool = False
    cf_zone_id: str | None = None
    dry_run: bool = False
    exclude_hostnames: frozenset[str] = frozenset()


def _get_bool(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    """Read a boolean env var. Raise on anything that is not clearly a bool.

    Accepts 1/0, true/false, yes/no, on/off (any case). A typo like
    ``DRY_RUN=ture`` must not silently turn into False.
    """
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ConfigError(
        f"{name} must be a boolean (1/0, true/false, yes/no, on/off), "
        f"got: {raw!r}"
    )


def _get_int(env: Mapping[str, str], name: str, default: int) -> int:
    """Read an integer env var. Raise a clear error if it is not a number."""
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a number, got: {raw!r}") from None
    if value <= 0:
        raise ConfigError(f"{name} must be greater than 0, got: {value}")
    return value


def _split_list(raw: str | None) -> frozenset[str]:
    """Split a comma list into clean, lower-case, non-empty items."""
    if not raw:
        return frozenset()
    return frozenset(
        item.strip().lower() for item in raw.split(",") if item.strip()
    )


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build a Config from env vars. Raise ConfigError if anything is missing."""
    if env is None:
        env = os.environ

    required = [
        "COOLIFY_URL",
        "COOLIFY_TOKEN",
        "CF_API_TOKEN",
        "CF_ACCOUNT_ID",
        "CF_TUNNEL_ID",
    ]
    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        raise ConfigError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    sync_dns = _get_bool(env, "SYNC_DNS")
    cf_zone_id = env.get("CF_ZONE_ID", "").strip() or None
    if sync_dns and not cf_zone_id:
        raise ConfigError("SYNC_DNS is on, so CF_ZONE_ID is required")

    coolify_url = env["COOLIFY_URL"].strip().rstrip("/")
    if not coolify_url.startswith(("http://", "https://")):
        raise ConfigError(
            "COOLIFY_URL must start with http:// or https://, "
            f"got: {coolify_url!r}"
        )

    return Config(
        coolify_url=coolify_url,
        coolify_token=env["COOLIFY_TOKEN"].strip(),
        cf_api_token=env["CF_API_TOKEN"].strip(),
        cf_account_id=env["CF_ACCOUNT_ID"].strip(),
        cf_tunnel_id=env["CF_TUNNEL_ID"].strip(),
        target_service=env.get("TARGET_SERVICE", "").strip()
        or DEFAULT_TARGET_SERVICE,
        poll_interval=_get_int(env, "POLL_INTERVAL", DEFAULT_POLL_INTERVAL),
        sync_dns=sync_dns,
        cf_zone_id=cf_zone_id,
        dry_run=_get_bool(env, "DRY_RUN"),
        exclude_hostnames=_split_list(env.get("EXCLUDE_HOSTNAMES")),
    )
