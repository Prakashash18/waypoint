# Deploying Waypoint

## Can this go on Vercel?

**Not the backend.** Four things were measured against Vercel's serverless
model, and each one rules it out on its own:

| Blocker | Measured | Vercel |
|---|---|---|
| Atlas CLI credentials | stored in an OS keyring, obtained through an interactive browser OAuth flow; the CLI reads no token env var | no persistent keyring, no shell to run the login |
| Playwright Chromium | 356 MB | 250 MB unzipped function limit |
| One planning run | 11.4 s | 10 s on Hobby |
| Runtime writes | screenshot captures + rate cache | filesystem read-only except `/tmp` |

**So yes — you need Render** (or Fly.io / Railway / any container host with a
shell and a persistent disk). The `Dockerfile` and `render.yaml` here are set up
for Render.

Vercel *could* host the React frontend on its own, but Flask already serves the
built bundle at `/app`, so a single Render service is simpler and avoids a
cross-origin setup. Split it only if you later want a CDN in front of the UI.

## Deploy to Render

1. Push this repo to GitHub.
2. Render → **New** → **Blueprint** → point at the repo. It reads `render.yaml`.
3. Set the secrets in the dashboard (they are `sync: false`, never in git):
   `OPENAI_API_KEY`, `RAPIDAPI_KEY`, `ELEVENLABS_API_KEY`,
   `AVIATIONSTACK_API_KEY`.
4. Deploy. `GET /api/health` reports what came up.

The blueprint asks for the **starter** plan because a persistent disk needs a
paid instance. Without the disk everything still runs, but the Atlas login and
the rate cache are lost on every restart.

## The one manual step: logging Atlas in

Everything else is configured by environment variable. Atlas is not — it uses an
interactive browser flow and keeps the result in a keyring. A fresh deploy comes
up with flights unavailable and says so:

```json
{"ready": {"atlas_cli": false},
 "notes": {"atlas_cli": "installed but not logged in — run: atlas-flight auth login"}}
```

Hotels, stays, screenshots, delays, locale and voice all work in that state; only
flights are missing, and the agent says they are missing rather than inventing
them. To enable flights, open a shell on the service (Render → **Shell**) and:

```bash
atlas-flight auth login --json     # prints an authorization_url
# open that URL in your own browser and complete the login
atlas-flight auth poll --json      # repeat until authenticated
atlas-flight auth status --json    # confirm
```

The container writes the credential to `/data/keyring` via the file backend
(`PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring`), so it survives
restarts and redeploys as long as the disk is mounted.

> That backend stores the token **unencrypted** on the mounted disk. Acceptable
> for a sandbox deployment you control; do not use it for a production
> credential without a real secret store.

## Running the container locally

```bash
docker build -t waypoint .
docker run --rm -p 8099:8000 --env-file .env -v waypoint-data:/data waypoint
```

Then open http://localhost:8099/app — verified working, including the built UI,
locale detection, live hotel rates and screenshots.

## What the image contains

- Python 3.12 + Flask, served by gunicorn (2 workers, 4 threads, 180 s timeout —
  a planning run makes several upstream calls)
- Chromium via Playwright, for screenshots of hotel websites and map views
- `atlas-flight-booking` from PyPI
- The React UI, **built inside the image** from `web/` so the bundle can never
  be stale relative to source

`/data` holds the Atlas keyring, screenshot captures and the hotel rate cache.
Keeping the cache there matters: the free RapidAPI tier is metered, and a cold
start would otherwise re-spend it.
