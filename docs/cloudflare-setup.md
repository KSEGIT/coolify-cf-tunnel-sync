# Cloudflare setup

This page shows how to get the four Cloudflare values the tool needs:

- `CF_API_TOKEN`
- `CF_ACCOUNT_ID`
- `CF_TUNNEL_ID`
- `CF_ZONE_ID` (only if you want DNS sync)

## 1. Create the API token

1. Go to the [Cloudflare dashboard](https://dash.cloudflare.com/).
2. Click your profile icon (top right) → **My Profile** → **API Tokens**.
3. Click **Create Token** → **Custom token** → **Get started**.
4. Give it a name, e.g. `coolify-tunnel-sync`.
5. Add this permission row:

   | Account | Cloudflare Tunnel | Edit |
   |---|---|---|

6. Only if you want DNS sync (`SYNC_DNS=true`), also add this row:

   | Zone | DNS | Edit |
   |---|---|---|

   Under **Zone Resources**, pick the zone (domain) your hostnames live in. Without this, set the zone row to cover your zone.

7. Under **Account Resources**, pick your account.
8. Click **Continue to summary** → **Create Token**.
9. Copy the token. Cloudflare shows it only once. This is your `CF_API_TOKEN`.

The tool never deletes anything, but Cloudflare has no "add-only" permission, so the token needs Edit.

## 2. Find the account id

1. Open the [Cloudflare dashboard](https://dash.cloudflare.com/).
2. Click any domain or **Workers & Pages**.
3. The account id is on the right side of the page, under **Account ID**. Copy it. This is `CF_ACCOUNT_ID`.

It is also in the URL: `https://dash.cloudflare.com/<account-id>/...`.

## 3. Find the tunnel id

1. In the dashboard, go to **Networks** → **Tunnels** (older dashboards: **Zero Trust** → **Networks** → **Tunnels**).
2. Click your tunnel.
3. The tunnel id (a UUID like `a1b2c3d4-...`) is shown on the page and in the URL. This is `CF_TUNNEL_ID`.

## 4. The tunnel must be remotely managed

The tool reads and writes tunnel config through the Cloudflare API. That only works when the config lives in Cloudflare.

- **Remotely managed** tunnel: you edit ingress rules in the dashboard. Config lives in Cloudflare. ✅ Works.
- **Locally managed** tunnel: you edit a `config.yml` on the server. Config lives on the server. ❌ Does not work.

To check: open your tunnel in the dashboard. If you can see and edit the **Public Hostnames** / ingress rules there, it is remotely managed.

If your tunnel is locally managed, migrate it first:

1. In the dashboard, create a new remotely managed tunnel.
2. Copy your hostnames from `config.yml` into the new tunnel's public hostnames.
3. Run `cloudflared` with the new tunnel token instead of the local `config.yml`.
4. Delete the old tunnel when everything works.

## 5. Find the zone id (only for DNS sync)

1. Open your domain in the Cloudflare dashboard.
2. On the **Overview** page, scroll down on the right side. **Zone ID** is listed there. This is `CF_ZONE_ID`.

Skip this if `SYNC_DNS=false`.

## ⚠️ Warning: never add `connectTimeout`

Remote-managed tunnels have a live bug: [cloudflared#1702](https://github.com/cloudflare/cloudflared/issues/1702). If `connectTimeout` appears in the remote tunnel config under `originRequest`, cloudflared fails to dial and connections break.

This tool never sets `connectTimeout`. Do not add it by hand in the dashboard either. If your tunnel config has it, remove it.
