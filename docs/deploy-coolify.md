# Deploy on Coolify

This guide shows you how to run `coolify-cf-tunnel-sync` on your own Coolify
server. You do not need to know Docker. Just follow the steps.

The tool watches your Coolify apps. When you give an app a new domain, the tool
adds that domain to your Cloudflare Tunnel for you.

## What you need before you start

- A running Coolify server.
- A Cloudflare account with a tunnel (the one that sends traffic to Coolify).
- About 10 minutes.

## Step 1: Create a Coolify API token

1. Open your Coolify dashboard.
2. Go to **Keys & Tokens** (in the menu under your user or team settings).
3. Create a new token. Read access is enough.
4. Copy the token and save it somewhere. You will need it in step 5.

## Step 2: Create a Cloudflare API token

1. Go to <https://dash.cloudflare.com>.
2. Click your profile icon (top right), then **My Profile**.
3. Open the **API Tokens** tab and click **Create Token**.
4. Choose **Create Custom Token**.
5. Give it a name, for example `coolify-tunnel-sync`.
6. Add this permission:
   - **Account** → **Cloudflare Tunnel** → **Edit**
7. If you want the tool to also create DNS records (`SYNC_DNS=true`), add:
   - **Zone** → **DNS** → **Edit**
8. Click **Continue to summary**, then **Create Token**.
9. Copy the token and save it. Cloudflare shows it only once.

## Step 3: Find your account id and tunnel id

1. Go to the Zero Trust dashboard: <https://one.dash.cloudflare.com>.
2. Look at the address bar. The URL looks like
   `https://one.dash.cloudflare.com/<ACCOUNT_ID>/...`.
   Copy the long hex part. That is your **account id**.
3. In the menu, go to **Networks** → **Tunnels**.
4. Click your tunnel. The **tunnel id** (a UUID) is shown on the page
   and also in the URL. Copy it.

## Step 4: Add the tool to Coolify

1. In Coolify, open your project and environment.
2. Click **Add Resource** → **Docker Compose (empty)**.
3. Copy the whole `docker-compose.yml` file from this repo and paste it in.

## Step 5: Set the environment variables

In the Coolify resource view, open **Environment Variables** and set:

| Variable | What to put in |
|---|---|
| `COOLIFY_URL` | Your Coolify URL, e.g. `https://coolify.example.com` |
| `COOLIFY_TOKEN` | The token from step 1 |
| `CF_API_TOKEN` | The token from step 2 |
| `CF_ACCOUNT_ID` | The account id from step 3 |
| `CF_TUNNEL_ID` | The tunnel id from step 3 |
| `DRY_RUN` | `true` (important for the first run) |

Optional:

| Variable | What it does |
|---|---|
| `TARGET_SERVICE` | Where new routes point. Default `http://localhost:8180`. |
| `POLL_INTERVAL` | Seconds between checks. Default `120`. |
| `SYNC_DNS` | Set `true` to also create DNS CNAME records. |
| `CF_ZONE_ID` | Your DNS zone id. Only needed if `SYNC_DNS=true`. |
| `EXCLUDE_HOSTNAMES` | Comma list of hostnames the tool must never touch. |

## Step 6: Deploy and watch the logs

1. Click **Deploy**.
2. Open the **Logs** tab.
3. Wait for the first cycle (it runs right away, then every `POLL_INTERVAL`
   seconds).
4. Because `DRY_RUN=true`, the tool only logs. It changes nothing.
   Look for lines like `would add N routes` or `added N routes`.
5. Check the hostnames in the log. Do they look right?

## Step 7: Turn off dry-run

1. Set `DRY_RUN=false` in the environment variables.
2. Redeploy.
3. Watch the logs again. You should see `added N routes`.
4. Open the tunnel in the Zero Trust dashboard. The new hostnames are now
   in the **Public Hostnames** list.

Done. The tool now keeps the tunnel in sync on its own.

## If something goes wrong

- **Container is unhealthy:** the tool has not finished a sync in a while.
  Check the logs for errors. Most often a token is wrong or missing.
- **`401` or `403` errors from Cloudflare:** the token lacks a permission.
  Redo step 2.
- **`401` from Coolify:** the Coolify token is wrong. Redo step 1.
- **Nothing is added, but you expect new routes:** check `DRY_RUN` is `false`
  and the hostnames are not in `EXCLUDE_HOSTNAMES`. Also remember: hostnames
  already covered by a wildcard rule are skipped on purpose.
