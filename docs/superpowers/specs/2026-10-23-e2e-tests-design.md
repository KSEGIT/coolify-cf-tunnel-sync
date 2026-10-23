# E2E tests: design

Date: 2026-10-23
Status: approved design, not built yet

## Goal

Test the real Docker image against the real Cloudflare API on each pull
request to `main`. Cover every feature the README promises.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Coolify | Fake server, no real Coolify | Real Coolify needs Postgres, Redis, Soketi and a token made inside the container. It adds 3-5 min per run and breaks easily. The tool uses only `GET /api/v1/applications`. |
| Cloudflare | Real API, test tunnel, test subdomain in an existing zone | No new domain needed. Tests own only `e2e-*` names. |
| Secrets | GitHub Environment `e2e` with a required reviewer | The repo is public. A person approves each run before the token is used. |
| Fork and Dependabot PRs | Job skips | GitHub gives them no Environment secrets. Run by hand with `workflow_dispatch` on that branch after review. |

GitHub docs, quoted: "When a Dependabot event triggers a workflow, the only
secrets available to the workflow are Dependabot secrets."
Never use `pull_request_target`: it would expose the token to fork code.

## Known gap

The fake Coolify cannot catch changes in the real Coolify API (for example a
new `fqdn` format). Unit tests in `tests/test_coolify.py` cover the formats we
know. Accept this gap for now.

## Parts

### 1. `e2e/fake_coolify/`

- `server.py`: Python standard library only (`http.server`). No new deps.
  - `GET /api/v1/applications`: needs `Authorization: Bearer <FAKE_COOLIFY_TOKEN>`.
    Wrong or missing token: HTTP 401. Returns the current app list as JSON,
    each item like `{"uuid": "...", "name": "...", "fqdn": "https://a.example.com,https://b.example.com"}`.
  - `POST /_apps`: test-only. Body is the new app list (JSON list). Replaces
    the list. Lets a test add a domain while the tool runs.
  - `GET /_health`: returns 200. Used to wait for start.
- `Dockerfile`: `FROM python:3.14-slim`, runs `server.py` on port 8000.

### 2. `e2e/test_e2e.py` and `e2e/conftest.py`

pytest tests. They use `docker` (subprocess) and `httpx` (already a dep).

Session setup:
1. Read env: `E2E_CF_API_TOKEN`, `E2E_CF_ACCOUNT_ID`, `E2E_CF_TUNNEL_ID`,
   `E2E_CF_ZONE_ID`, `E2E_BASE_DOMAIN`. If any is missing: fail with a clear
   message. Do not skip silently.
2. `docker build -t cfsync-e2e .` (the image from this PR).
3. `docker build -t fake-coolify-e2e e2e/fake_coolify`.
4. Create a Docker network. Start the fake Coolify on it as `fake-coolify`.
   The tool reaches it at `COOLIFY_URL=http://fake-coolify:8000`.
5. Save the current tunnel config as the restore point.

Per test:
1. Put the tunnel config to a known baseline (see below).
2. Set the fake app list with `POST /_apps`.
3. Start the tool container on the same network, with
   `COOLIFY_TOKEN` = the fake token. Also set `POLL_INTERVAL=5`,
   `TARGET_SERVICE=http://localhost:8180`, and the env for that test.
   Add `--health-interval=5s --health-start-period=0s` so the healthcheck
   runs fast.
4. Poll the Cloudflare API (timeout 60 s) until the expected state, or check
   the state did not change after at least 2 cycles (look for 2
   `cycle done` lines in `docker logs`).
5. Stop and remove the tool container.

Session teardown (always runs, also after failures):
1. Restore the saved tunnel config.
2. Delete every DNS record in the zone whose name matches
   `e2e-*.<E2E_BASE_DOMAIN>`. This also removes records left by older failed runs.
3. Remove containers and the network.

Baseline tunnel config (`ingress` list, in this order):
1. A route added by hand: `e2e-<run>-manual.<base>` -> `http://localhost:9999`.
2. A wildcard rule: `*.e2e-<run>-wild.<base>` -> `http://localhost:8180`.
3. Catch-all: `{"service": "http_status:404"}`.

`<run>` = `GITHUB_RUN_ID` in CI, or a random 8-char id locally.
All test hostnames: `e2e-<run>-<n>.<E2E_BASE_DOMAIN>`.

### 3. Test cases

| # | Test | Setup | Expect |
|---|---|---|---|
| 1 | Add route | 1 app with a new hostname | Route exists with `service` = `TARGET_SERVICE`. `http_status:404` is still last. |
| 2 | Idempotent | Same as 1, wait 2 more cycles | Tunnel config `version` does not change after the first add. No duplicate rule. |
| 3 | Hand-made route kept | App uses the manual hostname | Manual rule unchanged (still `http://localhost:9999`). No second rule. |
| 4 | Wildcard skip | App `x.e2e-<run>-wild.<base>` | No new rule. Log has `covered by a wildcard rule`. |
| 5 | Exclude | App hostname also in `EXCLUDE_HOSTNAMES` | No new rule. Log has `in EXCLUDE_HOSTNAMES`. |
| 6 | Dry run | `DRY_RUN=true`, new hostname | Config unchanged after 2 cycles. Log has `would add`. |
| 7 | DNS sync | `SYNC_DNS=true`, `CF_ZONE_ID` set | One proxied CNAME to `<tunnel>.cfargotunnel.com`. After 2 more cycles still exactly one. |
| 8 | No connectTimeout | After test 1 | No rule added by the tool has `originRequest.connectTimeout`. |
| 9 | Healthcheck | Any good run | `docker inspect` health status becomes `healthy`. |
| 10 | Late domain | Tool running, then `POST /_apps` adds a hostname | Route appears within the timeout. |

### 4. Keep e2e out of the normal test run

Add `pytest.ini` with `testpaths = tests`. Plain `pytest` keeps running only
unit tests. Run e2e with `pytest e2e`.

### 5. CI: new job in `.github/workflows/ghcr.yml`

```yaml
  e2e:
    name: e2e (real Cloudflare)
    needs: test
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (github.event_name == 'pull_request' &&
       github.event.pull_request.head.repo.full_name == github.repository &&
       github.actor != 'dependabot[bot]')
    runs-on: ubuntu-latest
    environment: e2e
    concurrency:
      group: e2e-cloudflare
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.14"
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest e2e -v
        env:
          E2E_CF_API_TOKEN: ${{ secrets.E2E_CF_API_TOKEN }}
          E2E_CF_ACCOUNT_ID: ${{ secrets.E2E_CF_ACCOUNT_ID }}
          E2E_CF_TUNNEL_ID: ${{ secrets.E2E_CF_TUNNEL_ID }}
          E2E_CF_ZONE_ID: ${{ secrets.E2E_CF_ZONE_ID }}
          E2E_BASE_DOMAIN: ${{ vars.E2E_BASE_DOMAIN }}
```

- `concurrency` stops two runs from using the tunnel at the same time.
- The `build` job does not depend on `e2e`. It does not run on PRs anyway.
- Check current action versions before you write the file.

### 6. Setup by hand (owner does this once)

Write this as `docs/e2e-setup.md`:

1. Create a new tunnel in Zero Trust > Networks > Tunnels. Pick
   "remotely managed". No `cloudflared` needs to run. Copy its UUID.
2. Pick a subdomain of an existing zone, for example `e2e.example.com`.
   Copy the zone id.
3. Create an API token with only:
   - Account > Cloudflare Tunnel > Edit (this account)
   - Zone > DNS > Edit (this zone)
4. In GitHub: Settings > Environments > New environment `e2e`.
   - Add yourself as required reviewer.
   - Add secrets `E2E_CF_API_TOKEN`, `E2E_CF_ACCOUNT_ID`,
     `E2E_CF_TUNNEL_ID`, `E2E_CF_ZONE_ID`.
   - Add variable `E2E_BASE_DOMAIN`.
5. To run e2e for a Dependabot or fork PR: read the diff first, then
   Actions > ghcr > Run workflow on that branch.

## Out of scope

- Real Coolify (nightly or otherwise).
- Running `cloudflared` or sending real traffic through the tunnel.
- Tests for Cloudflare API errors (unit tests cover them with `respx`).
