# Waypoint — a travel agent that books, and won't invent

A voice-first agentic travel planner. You describe a trip in one sentence and it
plans the whole thing — flights and stay priced together — then books it for
real: the fare re-verified with the airline, baggage priced per traveller per
leg, and an order created that holds actual seats.

It stops deliberately at payment. Everything up to that point is automated;
moving your money is not.

**The other half of the thesis is that it refuses to make things up.** Every
price, photograph and place carries the source it came from. When a provider
has nothing to say, the app says so rather than filling the gap — no stock
photography standing in for a hotel, no invented fare, no guessed link.

## Status

| | |
|---|---|
| **Running** | Locally, for testing — `venv/bin/python run.py`, then http://localhost:2000 |
| **Planned** | Alibaba Cloud ECS, Singapore region (`ap-southeast-1`) |

### TODO

- [ ] **Deploy to Alibaba Cloud** — written up in full below, and deliberately
      not done yet: Chromium needs ~450MB of headroom, which puts it above the
      free tier, and the cost is not worth carrying while the app is still
      changing daily. It runs locally in the meantime.
- [ ] Behind a proxy, set `proxy_buffering off` — the agent streams its progress
      over SSE, and a buffering proxy makes it arrive in one silent lump.
- [ ] Surface the Atlas account states (`TOP_UP_REQUIRED`,
      `TICKETING_ACTIVATION_REQUIRED`) in the UI; today a lapsed balance
      surfaces as a generic failure.
- [ ] Show voice input in the demo — it works, but it has never been recorded.

## Architecture

```
Browser (React, voice-first)
        │  one sentence in, cards + spoken reply out
        ▼
Flask  ──  /api/agent/stream    the agent's progress, as it happens (SSE)
           /api/booking/*       prepare · baggage · order · scan-passport
           /api/voice/*         ElevenLabs speech in and out
        │
        ▼
TripAgent — an OpenAI tool-calling loop over a registry of tools, each of
            which returns a result *and* the provenance of that result
        │
        ├── atlas_flights   Atlas CLI: search, verify, confirm price,
        │                   baggage, order — the booking spine
        ├── hotel_rates     Booking.com via RapidAPI (prices include tax)
        ├── places          OpenStreetMap: geocoding, airports, attractions
        ├── imagery         Playwright screenshots of the real property
        ├── locale          where the traveller is, for currency and origin
        └── websearch       Wikipedia / Nominatim place resolution
```

**No record without provenance.** Every tool returns a `Provenance` alongside
its data — `LIVE`, `CACHED`, `UNAVAILABLE`, `NOT_CONFIGURED` or `FAILED` — and
the UI shows it. A tool that cannot answer says so; none of them may invent a
substitute.

## Booking, and where it stops

Flights are booked through **Atlas**, which is what makes the booking real: the
fare is re-verified, baggage is priced per traveller per leg, and an order is
created that holds actual seats with a payment deadline.

Stays are **not** booked here. Each one links to the listing its rate was quoted
on; Waypoint never holds a room or takes a payment for one.

Payment is deliberately the traveller's own step. The order is settled on
Atlas, from an Atlas account balance — the app hands over the reference and the
link, and no agent moves money.

## Installation

### Prerequisites

- Python 3.12 (required by atlas-flight-booking)
- pipx (for isolated Python package installation)

### Install Atlas CLI

```bash
# Install pipx if not already installed
brew install pipx
pipx ensurepath

# Install atlas-flight-booking with Python 3.12
pipx install atlas-flight-booking --python python3.12

# Verify installation
atlas-flight --version
```

### Configure Environment

```bash
# Switch to sandbox environment (required for development)
atlas-flight environment use sandbox --json

# Authenticate
atlas-flight auth login
# Follow the login flow, then poll for completion:
atlas-flight auth poll

# Verify setup
atlas-flight doctor
```

### Install Waypoint

```bash
cd waypoint

# Create virtual environment (recommended)
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configure API Keys (Optional)

The app uses OpenAI for the agent loop and ElevenLabs for voice. Booking.com
rates come through RapidAPI. Put them in `.env`:

```bash
OPENAI_API_KEY=...        # the agent loop, and reading a passport's MRZ
ELEVENLABS_API_KEY=...    # speech in and out (optional; typing works too)
RAPIDAPI_KEY=...          # Booking.com hotel rates, via booking-com15
```

Everything else — OpenStreetMap, Wikipedia, ip-api — needs no key. Any provider
that is missing degrades honestly rather than silently.

## Usage

### Start the Server

```bash
python3.12 run.py
```

The UI will be available at http://localhost:2000

### End-to-End Flow

1. **Ask** — "Four nights in Ubud, 28 Sep to 2 Oct, two adults, with flights."
   Origin and currency come from the traveller's own location.
2. **Watch it work** — every tool call streams in as it runs, with its
   arguments, what came back, and how long it took.
3. **Compare** — three whole-trip options (cheapest, best value, best reviewed),
   each priced as both fares plus every night, taxes included.
4. **Explore** — open a stay for its own photographs and sources, or ask a
   follow-up in plain words and get answers on the map.
5. **Book the flight** — fare re-verified, baggage chosen, passenger details
   taken from a passport scan or typed in.
6. **Settle it yourself** — the order is created and holding seats; payment
   happens on Atlas, not here.

### API Endpoints

```bash
# Plan a trip (blocking), or stream the agent's progress
POST /api/agent/plan       {"request": "..."}
POST /api/agent/stream     {"request": "..."}       # SSE
POST /api/agent/cancel     {"session_id": "..."}

# Booking
POST /api/booking/prepare        {"offer_id": "..."}      # verify + price + baggage
POST /api/booking/baggage        {"booking_id", "traveler_id", "segment_id", "baggage_id"}
POST /api/booking/order          {"booking_id", "passengers": [...], "contact": {...}}
POST /api/booking/scan-passport  (multipart image)        # reads the MRZ

# Voice, context and housekeeping
POST /api/voice/transcribe   ·  POST /api/voice/speak
GET  /api/locale             ·  GET  /api/sources
GET  /api/settings/cache     ·  GET  /api/health
```

## Failure Handling

Every one of these is visible to the traveller rather than swallowed:

- **Price moved between search and booking** — Atlas reports the change itself;
  the card shows old and new, and nothing proceeds without a fresh decision.
- **Offer expired** — the CLI answers `terminal_error`/`OFFER_EXPIRED`, which
  the app surfaces as a failed step rather than a green tick.
- **A provider is down** — the card says which source had nothing. It will not
  substitute a stock photograph or an invented price.
- **RapidAPI quota exhausted** — saved prices are still served, explicitly
  labelled stale, with the reason.
- **An expired passport** — Atlas rejects it and names the field; the form says
  so in words rather than marking a box the traveller cannot see.

## Project Structure

```
src/
├── agent/
│   ├── trip_agent.py       the tool-calling loop, and its system prompt
│   ├── session.py          conversation memory, trimmed by whole turns
│   ├── api_tracker.py      what each provider cost, per call
│   └── flight_status.py    live delay lookups
├── tools/
│   ├── provenance.py       every record carries where it came from
│   ├── atlas_tool.py       flights: search, verify, price, baggage, order
│   ├── hotel_rates_tool.py Booking.com rates (tax included, fetched live)
│   ├── places_tool.py      OSM geocoding, airports, attractions
│   ├── imagery_tool.py     real photographs, or none at all
│   ├── mrz.py              passport machine-readable zone + check digits
│   └── locale_tool.py      where the traveller is
├── cli/wrapper.py          the Atlas CLI, matched to its real flags
└── ui/
    ├── app.py              Flask routes
    └── agent-app/          the built React UI (source in web/)

web/                        React + Vite source
scripts/                    demo recording, narration, fixtures
tests/api_smoke.py          every provider and endpoint, end to end
```

## Key Design Decisions

1. **Never invent** — a tool that cannot answer says so
2. **Never retry uncertain payments** — Mark indeterminate and stop
3. **Never persist passenger details** in logs (one-time input only)
4. **Treat all IDs as opaque** — Never parse, reformat, or regenerate
5. **Branch on envelope `code`** — Not HTTP status or exit codes
6. **Sandbox data never drives real decisions** — Clear warning in UI

## Limitations

- **Payment is not taken here** — by design. The order is settled on Atlas from
  an Atlas account balance; Waypoint hands over the reference and stops.
- **Stays are not booked** — every one links out to the listing its rate came
  from. No rooms are held.
- **Forward booking only** — no cancellations, refunds or changes.
- **Hotel availability comes from the provider** — Booking.com's search endpoint
  returns indicative room rates that do not vary with party size, and can list a
  property its own site shows as unavailable on those dates.
- **Not deployed** — runs locally; see the Alibaba Cloud TODO above.

Each of these is stated in the UI rather than hidden.

## Testing

```bash
# Every provider and endpoint, end to end, against live APIs
venv/bin/python tests/api_smoke.py stack endpoints
```

## Deployment

### Docker

The real `Dockerfile` at the repository root builds the UI with Node, installs
Playwright's Chromium for the hotel screenshots, and serves through gunicorn on
`$PORT` (8000 by default).

```bash
docker build -t waypoint .
docker run -p 8000:8000 --env-file .env waypoint
```

### Alibaba Cloud ECS (planned — not yet deployed)

**Why it is still a TODO:** Playwright's Chromium, which takes the hotel
photographs, peaks at roughly 450MB. That needs a 2GB instance to be safe,
which is above the free tier — and the app changes daily right now, so the
running cost is not yet worth it. Everything below is the intended path, not a
description of something already live.

Use a **Singapore** region. The app depends on OpenAI, ElevenLabs and RapidAPI
for nearly every request, and those are blocked or unreliable from mainland
regions — the app would degrade to "source unavailable" on almost every card,
which is the one failure mode it exists to prevent. Singapore also avoids the
ICP filing that a domain pointed at mainland servers requires.

```bash
# Build and push to a Singapore registry
docker build -t waypoint:latest .
docker tag waypoint:latest registry.ap-southeast-1.aliyuncs.com/<ns>/waypoint:latest
docker push registry.ap-southeast-1.aliyuncs.com/<ns>/waypoint:latest

# Run it. Chromium peaks around 450MB, so give the instance 2GB if you can.
docker run -d -p 80:8000 \
  -e OPENAI_API_KEY -e RAPIDAPI_KEY -e ELEVENLABS_API_KEY \
  -e ATLAS_KEYRING_B64 \
  registry.ap-southeast-1.aliyuncs.com/<ns>/waypoint:latest
```

Atlas keeps its credentials in an OS keyring, which a container does not have;
`scripts/export-atlas-credential.sh` packages one into `ATLAS_KEYRING_B64` for
the entrypoint to restore.

## Development Notes

### Atlas CLI Commands

```bash
# Search
atlas-flight search --origin KUL --destination SIN --depart 2026-09-15 --adults 1 --json

# List offers
atlas-flight offer list --search-id <search_id> --json

# Verify offer
atlas-flight offer verify --offer-id <offer_id> --json

# Confirm price
atlas-flight booking confirm-price --offer-id <offer_id> --json

# Select seat
atlas-flight booking seat --booking-id <booking_id> --preference auto --json

# Create order
atlas-flight order create --booking-id <booking_id> --passengers '<json>' --json

# Check status
atlas-flight order status --order-id <order_id> --json

# Pay
atlas-flight order pay --order-id <order_id> --payment-confirmation-id <id> --json
```

### JSON Envelope Format

Every CLI command returns:
```json
{
  "schema_version": "1",
  "status": "success|error|failure",
  "code": "SUCCESS|ERROR_CODE",
  "message": "Human-readable message",
  "retryable": false,
  "request_id": "uuid",
  "data": { ... },
  "details": { ... }
}
```

Branch on `code`, not `status`. All IDs are opaque strings.

## License

Apache-2.0

## Credits

Built for the Alibaba Cloud x Atlas Agentic AI Hackathon, Singapore.
Flights and booking by [Atlas](https://atlaslovestravel.com/); hotel rates from
Booking.com via RapidAPI; places and attractions from OpenStreetMap; voice by
ElevenLabs.
