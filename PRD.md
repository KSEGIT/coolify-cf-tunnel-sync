# PRD: coolify-cf-tunnel-sync

Status: v0.1 shipped (PR #4)
Owner: Daniel Kiska

## Problem

Coolify sets a domain on an app. Cloudflare Tunnel does not learn about it.
A human must open the Cloudflare dashboard and add the hostname by hand.
Forget once, and the new app shows a 404. Do it often, and it wastes time.

## Goal

Add a domain in Coolify. Wait two minutes. The domain works.
No clicks in the Cloudflare dashboard.

## Users

One user first: me, running one Coolify server and one Cloudflare Tunnel.
Built so anyone with the same setup can use it.

## Requirements

Must:

- Read app domains from the Coolify API.
- Add missing hostnames to the tunnel config through the Cloudflare API.
- Never delete or change a route it did not add.
- Keep the catch-all `http_status:404` rule last.
- Skip hostnames a wildcard rule already covers.
- Run as one container, deployed in Coolify itself.
- Config through env vars only. No files, no database.
- Dry-run mode for a safe first run.
- Healthcheck that fails when sync stops working.

Should:

- Create DNS CNAME records when asked (`SYNC_DNS=true`).
- Retry failed DNS records on the next cycle.
- Publish the image to GHCR on every merge to main.

Won't (non-goals):

- No UI. Logs are the UI.
- No webhook. Coolify has no event for "domain changed". Polling is the design.
- No route removal. Deleting routes by hand in the dashboard stays a manual job.
- No changes to Coolify itself.
- No support for locally-managed tunnels (config.yml on disk).

## Design (short)

Poll loop, every 120 s by default:

1. `GET /api/v1/applications` on Coolify. Collect bare hostnames.
2. `GET` tunnel config from Cloudflare.
3. Diff. Build new rules pointing at Traefik (`http://localhost:8180`).
4. `PUT` the merged config back. New rules go before the catch-all.
5. Optional: add CNAME `<hostname>` → `<tunnel-id>.cfargotunnel.com`.
6. Sleep. Repeat. A failed cycle logs and retries next round.

Hard rule: never set `connectTimeout` in remote config. Cloudflare bug
(cloudflared#1702) breaks connections when it is set.

## Success check

- Add a domain in Coolify. Within one poll interval, the tunnel config has it.
- Container restarts, API errors, bad tokens: tool logs and recovers.
- Fresh Ubuntu install: deploy compose, set 5 env vars, done.

## Later (not planned now)

- Remove routes for deleted Coolify apps (behind a flag, off by default).
- Metrics endpoint for Prometheus.
- Multiple tunnels or multiple Coolify servers in one container.
