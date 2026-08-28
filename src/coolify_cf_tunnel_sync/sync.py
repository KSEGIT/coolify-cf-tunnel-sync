"""The reconciler: make the tunnel config match the Coolify domains.

Hard rules (see DESIGN.md):
- Additive only. Never remove or edit an existing rule.
- The catch-all rule (the one with no hostname) stays last.
- Skip hostnames already covered by a wildcard rule.
- Never set connectTimeout in originRequest (cloudflared bug #1702).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .cloudflare import CloudflareClient
from .config import Config
from .coolify import CoolifyClient

log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """What one sync cycle did (or would do in dry-run mode)."""

    added: list[str] = field(default_factory=list)
    present: list[str] = field(default_factory=list)
    covered_by_wildcard: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    dns_created: list[str] = field(default_factory=list)
    dns_present: int = 0
    dry_run: bool = False


def is_covered_by_wildcard(hostname: str, wildcard: str) -> bool:
    """Check if a wildcard rule like *.example.com covers a hostname.

    Only one extra label matches: app.example.com is covered by
    *.example.com, but deep.app.example.com and example.com are not.
    """
    if not wildcard.startswith("*."):
        return False
    suffix = wildcard[1:]  # ".example.com"
    if not hostname.endswith(suffix):
        return False
    prefix = hostname[: -len(suffix)]
    # The prefix is the extra label. It must be non-empty and have no dots.
    return bool(prefix) and "." not in prefix


def build_rule(hostname: str, target_service: str) -> dict[str, Any]:
    """Build one new ingress rule in the exact shape from DESIGN.md.

    No connectTimeout on purpose: it breaks remote-managed tunnels
    (cloudflared bug #1702).
    """
    return {
        "hostname": hostname,
        "service": target_service,
        "originRequest": {
            "noTLSVerify": True,
            "disableChunkedEncoding": True,
        },
    }


def insert_before_catch_all(
    ingress: list[dict[str, Any]], new_rules: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return a new list with the new rules before the catch-all rule.

    The catch-all is the first rule with no hostname (usually
    service: http_status:404). Existing rules are not touched.
    """
    catch_all_index = next(
        (i for i, rule in enumerate(ingress) if not rule.get("hostname")),
        len(ingress),
    )
    return ingress[:catch_all_index] + new_rules + ingress[catch_all_index:]


def find_missing(
    ingress: list[dict[str, Any]],
    domains: set[str],
    exclude: frozenset[str],
) -> tuple[list[str], SyncResult]:
    """Split the wanted domains into: to add, covered, excluded, present."""
    # Lower-case everything: Coolify hostnames are already lower-cased in
    # parse_fqdn, but the tunnel config may hold mixed-case hostnames, and a
    # case mismatch would cause a duplicate add or a missed wildcard.
    existing = {
        h.lower()
        for rule in ingress
        if isinstance((h := rule.get("hostname")), str) and h
    }
    wildcards = [h for h in existing if h.startswith("*.")]

    result = SyncResult()
    to_add: list[str] = []
    for host in sorted(domains):
        if host in exclude:
            result.excluded.append(host)
        elif host in existing:
            result.present.append(host)
        elif any(is_covered_by_wildcard(host, w) for w in wildcards):
            result.covered_by_wildcard.append(host)
        else:
            to_add.append(host)
    return to_add, result


def run_sync(
    config: Config, coolify: CoolifyClient, cloudflare: CloudflareClient
) -> SyncResult:
    """Run one sync cycle: diff, then add what is missing.

    In dry-run mode nothing is written. Returns a SyncResult.
    """
    domains = coolify.get_domains()
    tunnel_config = cloudflare.get_tunnel_config()
    ingress = tunnel_config.get("ingress") or []

    to_add, result = find_missing(ingress, domains, config.exclude_hostnames)
    result.dry_run = config.dry_run
    result.added = to_add

    for host in result.covered_by_wildcard:
        log.info("skip %s: covered by a wildcard rule", host)
    for host in result.excluded:
        log.info("skip %s: in EXCLUDE_HOSTNAMES", host)

    if to_add:
        if config.dry_run:
            for host in to_add:
                log.info(
                    "dry-run: would add %s -> %s", host, config.target_service
                )
        else:
            new_rules = [
                build_rule(host, config.target_service) for host in to_add
            ]
            tunnel_config["ingress"] = insert_before_catch_all(
                ingress, new_rules
            )
            cloudflare.put_tunnel_config(tunnel_config)
            for host in to_add:
                log.info("added %s -> %s", host, config.target_service)

    # DNS runs for new routes and for routes already in the tunnel: a CNAME
    # may still be missing because an earlier cycle failed after the PUT.
    # In dry-run mode nothing is written, so DNS is skipped there too.
    if config.sync_dns and not config.dry_run:
        for host in to_add + result.present:
            if cloudflare.ensure_cname(host):
                result.dns_created.append(host)
                log.info("created DNS CNAME for %s", host)
            else:
                result.dns_present += 1
                log.info("DNS CNAME for %s already exists", host)

    return result
