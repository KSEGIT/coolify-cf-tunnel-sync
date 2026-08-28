# Troubleshooting

Find your symptom in the table. Then read the notes below for details.

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` from Cloudflare | Token missing Tunnel:Edit, or wrong token | Make a new token with Account > Cloudflare Tunnel > Edit. See [cloudflare-setup.md](cloudflare-setup.md). |
| `401` from Coolify | Wrong or expired Coolify token | Make a new API token in Coolify. Read access is enough. |
| Routes added, but the site shows `502` | `TARGET_SERVICE` does not reach Coolify's Traefik | Check `TARGET_SERVICE`. See the 502 note below. |
| Log says "skipped, wildcard covers it" | A wildcard rule already covers the hostname | Nothing is wrong. This is expected. |
| Error: tunnel is locally managed | The tunnel config lives in a local `config.yml` | Migrate to a remotely managed tunnel. See [cloudflare-setup.md](cloudflare-setup.md#4-the-tunnel-must-be-remotely-managed). |
| DNS sync fails: record already exists | An A record (or other record) with that name already exists | Delete the old record by hand, or leave it and the tool skips that name. |

## 401 from Cloudflare

Cloudflare checked your `CF_API_TOKEN` and said no.

- The token must have **Account > Cloudflare Tunnel > Edit**.
- For DNS sync it also needs **Zone > DNS > Edit** on your zone.
- Tokens are shown only once at creation. If you lost it, make a new one.
- Check you did not mix up the token with the account id or tunnel id.

## 401 from Coolify

Coolify checked your `COOLIFY_TOKEN` and said no.

- Make a token in Coolify under **Keys & Tokens** → **API tokens**.
- Read permission is enough. The tool only lists applications.
- Check `COOLIFY_URL` has no trailing path, e.g. `https://coolify.example.com`.

## Routes added but the site shows 502

The tunnel sends traffic to `TARGET_SERVICE` and nothing answers there.

- Default is `http://localhost:8180`, which is Coolify's Traefik proxy. That only works if this container shares the network namespace with Traefik.
- If you run this tool as a normal separate container, `localhost` points at the tool itself, not Traefik. Two options:
  - Set `TARGET_SERVICE` to Traefik's reachable address, e.g. `http://coolify-proxy:80` on the Coolify Docker network.
  - Or run the container with `network_mode: "service:<traefik-service>"` (or `network_mode: host` where that fits) so `localhost:8180` really is Traefik.
- Test from inside the container: `docker exec <container> wget -qO- http://localhost:8180` should return something.

## "Skipped, wildcard covers it"

Your tunnel config has a wildcard rule like `*.example.com`. The hostname you set in Coolify matches it. The tool skips it on purpose — adding a second route would be duplicate work. The site should already work through the wildcard.

If the site does not work, check where the wildcard rule points. It may send traffic to the wrong service.

## Tunnel is locally managed

The tool can only change tunnels whose config lives in Cloudflare (remotely managed). A locally managed tunnel reads a `config.yml` on your server, and the API will refuse changes.

There is no flag to force it. Migrate the tunnel to remote management first. Steps are in [cloudflare-setup.md](cloudflare-setup.md#4-the-tunnel-must-be-remotely-managed).

## DNS record conflict

`SYNC_DNS=true` and the tool tried to create a CNAME, but a record with that name already exists — often an old A record. Cloudflare allows only one of CNAME or A for the same name.

- The tool does not delete records. It logs the conflict and moves on.
- Fix it by hand in the Cloudflare dashboard: delete the old record, then wait for the next run. The tool will add the CNAME.
- If the existing record is correct and you do not want a CNAME, add that name to `EXCLUDE_HOSTNAMES` or turn off `SYNC_DNS`.

## Still stuck

Run with `DRY_RUN=true` and read the log. It shows exactly what the tool would change, with no writes. That is the fastest way to see what it thinks the world looks like.
