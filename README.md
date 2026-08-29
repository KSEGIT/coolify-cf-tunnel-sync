# coolify-cf-tunnel-sync

[![GHCR image](https://img.shields.io/badge/ghcr.io-ksegit%2Fcoolify--cf--tunnel--sync-blue)](https://ghcr.io/ksegit/coolify-cf-tunnel-sync)

Keep your Cloudflare Tunnel in sync with your Coolify apps. When you set a domain on an app in Coolify, this tool adds that hostname to your Cloudflare Tunnel for you. No more editing tunnel config by hand.

## How it works

The tool is one small container. It runs a loop:

1. Ask the Coolify API for all apps and their domains.
2. Ask the Cloudflare API for the current tunnel config.
3. Find domains that Coolify knows but the tunnel does not.
4. Add those domains to the tunnel config. Nothing is ever removed.
5. Optionally add a DNS CNAME record for each new domain.

Then it sleeps and runs again. Safe to run every minute. Same input, same output.

Rules it always follows:

- It only adds routes. It never deletes or edits routes it did not add.
- The catch-all `http_status:404` rule always stays last.
- If a wildcard rule already covers a hostname, it skips that hostname.
- It never sets `connectTimeout`. That field breaks remote tunnels (cloudflared bug #1702).

## Quickstart

Add this service to your Coolify Docker Compose stack:

```yaml
services:
  tunnel-sync:
    image: ghcr.io/ksegit/coolify-cf-tunnel-sync:latest
    environment:
      COOLIFY_URL: https://coolify.example.com
      COOLIFY_TOKEN: your-coolify-api-token
      CF_API_TOKEN: your-cloudflare-api-token
      CF_ACCOUNT_ID: your-cloudflare-account-id
      CF_TUNNEL_ID: your-tunnel-uuid
    restart: unless-stopped
```

Five env vars are required: `COOLIFY_URL`, `COOLIFY_TOKEN`, `CF_API_TOKEN`, `CF_ACCOUNT_ID`, `CF_TUNNEL_ID`. Set `DRY_RUN: "true"` first if you want to see what it would do before it writes anything.

Your tunnel must be **remotely managed** (the config lives in Cloudflare, not in a local `config.yml`). See [docs/cloudflare-setup.md](docs/cloudflare-setup.md) for how to make the API token and find the ids.

## Environment variables

| Var | Required | Default | Meaning |
|---|---|---|---|
| `COOLIFY_URL` | yes | — | e.g. `https://coolify.example.com` |
| `COOLIFY_TOKEN` | yes | — | Coolify API token (read access is enough) |
| `CF_API_TOKEN` | yes | — | Cloudflare token, Tunnel:Edit (+ DNS:Edit if DNS sync on) |
| `CF_ACCOUNT_ID` | yes | — | Cloudflare account id |
| `CF_TUNNEL_ID` | yes | — | Tunnel UUID |
| `TARGET_SERVICE` | no | `http://localhost:8180` | Where new routes point |
| `POLL_INTERVAL` | no | `120` | Seconds between runs |
| `SYNC_DNS` | no | `false` | Also create CNAME records |
| `CF_ZONE_ID` | only if `SYNC_DNS` | — | DNS zone for CNAMEs |
| `DRY_RUN` | no | `false` | Log only, no writes |
| `EXCLUDE_HOSTNAMES` | no | — | Comma list to never touch |

## Docs

- [Cloudflare setup](docs/cloudflare-setup.md) — API token, account id, tunnel id, remote-managed tunnels.
- [Troubleshooting](docs/troubleshooting.md) — common errors and how to fix them.

## License

MIT. See [LICENSE](LICENSE).
