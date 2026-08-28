"""Entrypoint: run one sync cycle, then loop forever with a sleep.

Run with: python -m coolify_cf_tunnel_sync
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Touched after each good cycle. The Docker HEALTHCHECK reads it.
LAST_SYNC_OK = Path("/tmp/last_sync_ok")

from .cloudflare import CloudflareClient
from .config import ConfigError, load_config
from .coolify import CoolifyClient
from .sync import run_sync

log = logging.getLogger("coolify_cf_tunnel_sync")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    try:
        config = load_config()
    except ConfigError as exc:
        log.error("config error: %s", exc)
        return 1

    log.info(
        "starting: poll every %ss, target %s, dry_run=%s, sync_dns=%s",
        config.poll_interval,
        config.target_service,
        config.dry_run,
        config.sync_dns,
    )

    with (
        CoolifyClient(config.coolify_url, config.coolify_token) as coolify,
        CloudflareClient(
            config.cf_api_token,
            config.cf_account_id,
            config.cf_tunnel_id,
            zone_id=config.cf_zone_id,
        ) as cloudflare,
    ):
        while True:
            try:
                result = run_sync(config, coolify, cloudflare)
                if result.added:
                    verb = "would add" if result.dry_run else "added"
                    log.info(
                        "cycle done: %s %d route(s): %s",
                        verb,
                        len(result.added),
                        ", ".join(result.added),
                    )
                else:
                    log.info("cycle done: nothing to add, tunnel is up to date")
                LAST_SYNC_OK.touch()
            except Exception:
                # One bad cycle must not kill the loop.
                log.exception("cycle failed; will try again after the sleep")
            time.sleep(config.poll_interval)


if __name__ == "__main__":
    sys.exit(main())
