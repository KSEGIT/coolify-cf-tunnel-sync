"""Small client for the Cloudflare API.

Used for two things:
- Read and write the tunnel ingress config.
- Optionally create DNS CNAME records for new hostnames.

Every Cloudflare API answer has a "success" field. We always check it.
"""

from __future__ import annotations

from typing import Any

import httpx

API_BASE = "https://api.cloudflare.com"


class CloudflareError(Exception):
    """Raised when the Cloudflare API reports success=false or bad HTTP."""


class CloudflareClient:
    """Client for the tunnel config and (optionally) DNS records."""

    def __init__(
        self,
        api_token: str,
        account_id: str,
        tunnel_id: str,
        zone_id: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.tunnel_id = tunnel_id
        self.zone_id = zone_id
        self._config_url = (
            f"/client/v4/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"
        )
        self._dns_url = f"/client/v4/zones/{zone_id}/dns_records" if zone_id else None
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CloudflareClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _check(self, response: httpx.Response) -> dict[str, Any]:
        """Parse the answer and raise CloudflareError if it is not a success."""
        if response.status_code >= 400:
            raise CloudflareError(
                f"Cloudflare API returned HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
        data = response.json()
        if not data.get("success"):
            errors = data.get("errors") or []
            raise CloudflareError(f"Cloudflare API error: {errors}")
        return data

    def get_tunnel_config(self) -> dict[str, Any]:
        """Fetch the current tunnel config (the dict with the ingress list)."""
        data = self._check(self._client.get(self._config_url))
        result = data.get("result") or {}
        return result.get("config") or {}

    def put_tunnel_config(self, config: dict[str, Any]) -> None:
        """Write the tunnel config back. The whole config goes in one PUT."""
        self._check(self._client.put(self._config_url, json={"config": config}))

    def _require_dns_url(self) -> str:
        if not self._dns_url:
            raise CloudflareError("DNS sync needs CF_ZONE_ID, but none was set")
        return self._dns_url

    def cname_exists(self, hostname: str) -> bool:
        """Check if a CNAME for this hostname already exists in the zone."""
        data = self._check(
            self._client.get(
                self._require_dns_url(),
                params={"type": "CNAME", "name": hostname},
            )
        )
        return bool(data.get("result"))

    def create_cname(self, hostname: str) -> None:
        """Create CNAME <hostname> -> <tunnel-id>.cfargotunnel.com (proxied)."""
        self._check(
            self._client.post(
                self._require_dns_url(),
                json={
                    "type": "CNAME",
                    "name": hostname,
                    "content": f"{self.tunnel_id}.cfargotunnel.com",
                    "proxied": True,
                    "comment": "managed by coolify-cf-tunnel-sync",
                },
            )
        )

    def ensure_cname(self, hostname: str) -> bool:
        """Create the CNAME if it is missing. Return True if one was created."""
        if self.cname_exists(hostname):
            return False
        self.create_cname(hostname)
        return True
