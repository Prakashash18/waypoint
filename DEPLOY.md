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

## Deploy to Render (free plan)

1. Render → **New** → **Blueprint** → pick the repo. It reads `render.yaml`.
2. Render prompts for the five `sync: false` variables. Paste:
   - `OPENAI_API_KEY` — required; without it the agent cannot plan at all
   - `RAPIDAPI_KEY` — hotel rates, review scores, photographs
   - `ELEVENLABS_API_KEY` — voice in and out
   - `AVIATIONSTACK_API_KEY` — live flight delays
   - `ATLAS_KEYRING_B64` — flights; see below. Leave blank to deploy without them.
3. **Apply**. First build takes roughly 5–8 minutes; Chromium is the slow part.
4. `GET /api/health` reports what came up. The app is at `/app`.

### What the free plan costs you

- **Sleeps after 15 minutes idle.** The first request afterwards takes ~30 s.
- **No persistent disk.** The hotel rate cache is lost on each cold start, so
  the metered RapidAPI free tier gets re-spent.
- **No shell.** This is what forces `ATLAS_KEYRING_B64` below.
- **512 MB.** A screenshot peaks around 450 MB. If you see the instance being
  killed mid-request, set `WAYPOINT_DISABLE_SCREENSHOTS=true`; hotels from the
  rate provider already carry real photographs, so you mainly lose the map
  fallback.

To move to Starter later: set `plan: starter` in `render.yaml` and add the disk
block shown at the bottom of that file.

## Flights: getting the Atlas credential onto the server

Everything else is an environment variable. Atlas is not — it authorises through
an interactive browser flow and stores the result in an OS keyring. On a plan
with a shell you would just run `atlas-flight auth login` on the server. The free
plan has no shell, so you move the credential you already hold instead.

On your own machine, once:

```bash
atlas-flight auth status --json          # confirm you are logged in
./scripts/export-atlas-credential.sh     # prints one base64 line
```

macOS will ask permission to read the Keychain. Copy the line into Render as
`ATLAS_KEYRING_B64`. The container restores it into its keyring at boot; the
startup log says `atlas: credential restored from ATLAS_KEYRING_B64`.

> **Treat that value as a password** — it authorises bookings on your Atlas
> account. It lives only in Render's environment, never in the repo or the
> image, and the container stores it with keyring's plaintext file backend.
> Rotate it by running `atlas-flight auth login` again and re-exporting.

Without it the app still runs and says so:

```json
{"ready": {"atlas_cli": false},
 "notes": {"atlas_cli": "installed but not logged in — run: atlas-flight auth login"}}
```

Hotels, stays, screenshots, delays, locale and voice all work in that state.
Only flights are missing, and the agent says they are missing rather than
inventing them — verified by running the container with no credential.

## Running the container locally

```bash
docker build -t waypoint .
docker run --rm -p 8099:8000 --env-file .env waypoint
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

Runtime state (Atlas keyring, screenshot captures, hotel rate cache) lives under
`/var/waypoint`. On a paid plan, mount a disk there — keeping the rate cache
matters because the free RapidAPI tier is metered and a cold start re-spends it.
