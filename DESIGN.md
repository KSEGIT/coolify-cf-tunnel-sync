# Design: coolify-cf-tunnel-sync

## Problem

Coolify sets a domain on an app. Cloudflare Tunnel does not know about it.
Someone must add the hostname to the tunnel config by hand. This tool does that job.

## What it does

A small container. It runs a loop:

1. Ask the Coolify API for all applications and their domains (fqdn).
2. Ask the Cloudflare API for the current tunnel config.
3. Find hostnames that are in Coolify but not in the tunnel config.
4. Add them to the tunnel config (GET → modify → PUT).
5. Optionally add a DNS CNAME record for each new hostname.
6. Sleep. Repeat.

## Rules (hard)

- **Additive only.** It never removes a route. It never edits a route it did not add.
- **Catch-all stays last.** New rules go before the final `http_status:404` rule.
- **Skip covered names.** If a wildcard rule (e.g. `*.coolify.kse-design.pl`) already
  covers a hostname, do not add it.
- **Never set `connectTimeout`.** Remote-managed tunnels have a live bug
  (cloudflared#1702): `connectTimeout` in the config breaks dials. Leave it out.
- **Idempotent.** Same input, same output. Safe to run every minute.
- **Dry-run mode.** Log what would change. Change nothing.

## New route shape

```
hostname: <app domain>
service: http://localhost:8180        # Coolify Traefik, configurable
originRequest:
  noTLSVerify: true
  disableChunkedEncoding: true
```

## Tech choices

- Python 3.12, slim image. `httpx` for HTTP. No framework.
- Single container. Config through env vars only. No state files.
- Poll-based. Coolify has no webhook for "domain changed", so polling is the design.
  Default interval: 120 s.

## Env vars

| Var | Required | Default | Meaning |
|---|---|---|---|
| `COOLIFY_URL` | yes | — | e.g. `https://coolify.kse-design.pl` |
| `COOLIFY_TOKEN` | yes | — | Coolify API token (read is enough) |
| `CF_API_TOKEN` | yes | — | Cloudflare token, Tunnel:Edit (+ DNS:Edit if DNS sync on) |
| `CF_ACCOUNT_ID` | yes | — | Cloudflare account id |
| `CF_TUNNEL_ID` | yes | — | Tunnel UUID |
| `TARGET_SERVICE` | no | `http://localhost:8180` | Where new routes point |
| `POLL_INTERVAL` | no | `120` | Seconds between runs |
| `SYNC_DNS` | no | `false` | Also create CNAME records |
| `CF_ZONE_ID` | only if SYNC_DNS | — | DNS zone for CNAMEs |
| `DRY_RUN` | no | `false` | Log only, no writes |
| `EXCLUDE_HOSTNAMES` | no | — | Comma list to never touch |

## APIs used

- Coolify v1: `GET /api/v1/applications` (Bearer token). fqdn field holds domains.
- Cloudflare: `GET/PUT /client/v4/accounts/{id}/cfd_tunnel/{tid}/configurations`
- Cloudflare DNS (optional): `POST /client/v4/zones/{zid}/dns_records` (CNAME → `<tunnel-id>.cfargotunnel.com`, proxied)

## Repo layout

```
src/coolify_cf_tunnel_sync/  # the tool
tests/                       # unit tests, mocked HTTP
docs/                        # setup + troubleshooting
Dockerfile
docker-compose.yml           # for Coolify deploy
.github/workflows/ghcr.yml   # build + push to GHCR
```

## Deploy

User adds it as a Docker Compose service in Coolify itself, sets the env vars, done.
Image: `ghcr.io/ksegit/coolify-cf-tunnel-sync:latest`.
