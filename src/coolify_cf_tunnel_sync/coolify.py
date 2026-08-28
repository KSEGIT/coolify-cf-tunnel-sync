"""Small client for the Coolify v1 API.

We only read data: the list of applications and their domains (fqdn).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx


class CoolifyError(Exception):
    """Raised when the Coolify API answers with an error or bad data."""


def _to_hostname(value: str) -> str | None:
    """Turn one fqdn entry into a bare hostname.

    Handles full URLs (https://app.example.com/path), bare hosts,
    ports, and trailing dots. Returns None for empty junk.
    """
    value = value.strip()
    if not value:
        return None
    # urlsplit only fills netloc when there is a scheme, so add one if missing.
    if "://" not in value:
        value = "//" + value
    netloc = urlsplit(value).netloc
    # Drop userinfo (user@host) and port (host:8080).
    host = netloc.split("@")[-1].split(":")[0]
    host = host.strip().strip(".").lower()
    return host or None


def parse_fqdn(fqdn: Any) -> set[str]:
    """Extract bare hostnames from a Coolify fqdn field.

    The field can be a string like "https://a.com, https://b.com/x"
    or a list of such strings. Anything else yields an empty set.
    """
    if not fqdn:
        return set()
    if isinstance(fqdn, str):
        parts = fqdn.split(",")
    elif isinstance(fqdn, list):
        parts = []
        for item in fqdn:
            parts.extend(str(item).split(","))
    else:
        return set()
    return {host for part in parts if (host := _to_hostname(part))}


class CoolifyClient:
    """Read-only client for the Coolify API."""

    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CoolifyClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_applications(self) -> list[dict[str, Any]]:
        """Fetch all applications. Raise CoolifyError on failure."""
        response = self._client.get("/api/v1/applications")
        if response.status_code != 200:
            raise CoolifyError(
                f"Coolify API returned HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
        data = response.json()
        if not isinstance(data, list):
            raise CoolifyError("Coolify API did not return a list of apps")
        return data

    def get_domains(self) -> set[str]:
        """Return the set of bare hostnames across all applications."""
        domains: set[str] = set()
        for app in self.get_applications():
            if isinstance(app, dict):
                domains.update(parse_fqdn(app.get("fqdn")))
        return domains
