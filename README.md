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

- [ ] **Deploy to Alibaba Cloud.** ECS in **Singapore**, not a mainland region:
      the app calls OpenAI, ElevenLabs and RapidAPI on nearly every request, and
      those are unreachable or unreliable from mainland regions. Singapore also
      avoids the ICP filing a mainland-hosted domain requires.
- [ ] Behind a proxy, set `proxy_buffering off` — the agent streams its progress
      over SSE, and a buffering proxy makes it arrive in one silent lump.
- [ ] Surface the Atlas account states (`TOP_UP_REQUIRED`,
      `TICKETING_ACTIVATION_REQUIRED`) in the UI; today a lapsed balance
      surfaces as a generic failure.
- [ ] Show voice input in the demo — it works, but it has never been recorded.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Waypoint Agent                          │
├─────────────────────────────────────────────────────────────┤
│  UI Layer (Flask + React)                                    │
│  • Disruption intake form                                    │
│  • Checkpoint decision cards                                 │
│  • Audit trail viewer                                        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  Agent Orchestration                                         │
│  • SearchEngine: Find & rank replacement flights             │
│  • CheckpointManager: 4 mandatory approval checkpoints       │
│  • AuditTrail: Append-only decision log                      │
│  • ReasoningEngine: Qwen-powered tradeoff generation         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  CLI Wrapper Layer                                           │
│  • Subprocess calls to atlas-flight CLI                      │
│  • JSON envelope parser                                      │
│  • Error taxonomy & retry logic                              │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  atlas-flight CLI  │
                    │  (Apache-2.0)      │
                    └───────────────────┘
```

## Four Mandatory Checkpoints

1. **Initial Booking Authorization** — Present ranked options, get permission to proceed
2. **Price Change Acceptance** — Fare moved between search and verify; explicit re-confirmation required
3. **Seat Fallback Selection** — Preferred seat unavailable; approve auto-assignment
4. **Final Payment Summary** — Show total, confirm payment from Atlas balance

Each checkpoint displays:
- What permission is being requested
- Agent's reasoning
- What changed since the last checkpoint
- Exact CLI command that will execute
- Approve / Reject / Ask Question buttons

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

For Qwen-powered reasoning (via Alibaba Cloud Model Studio):

```bash
export DASHSCOPE_API_KEY="your-api-key-here"
```

Without the API key, the system uses template-based reasoning.

## Usage

### Start the Server

```bash
python3.12 run.py
```

The UI will be available at http://localhost:2000

### End-to-End Flow

1. **Disruption Intake**: Enter cancelled flight details (origin, destination, departure time, passengers, hard deadline)

2. **Options Display**: Agent searches and ranks replacement flights with tradeoff descriptions:
   - "Cheapest but arrives 4h after your deadline"
   - "Only option that makes the meeting, +$180"
   - "Best overall value"

3. **Select Option**: Click on preferred option → Checkpoint 1 fires

4. **Approve Checkpoints**: At each checkpoint, review:
   - Agent's reasoning
   - What changed (especially price movements)
   - Exact CLI command
   - Approve or reject

5. **Ticket Issuance**: After final approval, agent executes:
   - `offer verify` → `booking confirm-price` → `booking seat` → `order create` → `order pay`
   - Polls `order status` until ticket issued (up to 120s)

6. **Export Audit Trail**: Download complete audit log (JSON or CSV) with timestamps, request IDs, and all decisions

### API Endpoints

```bash
# Submit disruption
POST /api/disruption
{
  "origin": "KUL",
  "destination": "SIN",
  "original_departure": "2026-09-15T08:00:00",
  "passengers": 1,
  "hard_deadline": "2026-09-15T13:00:00"
}

# Get ranked options
GET /api/options

# Select option (triggers Checkpoint 1)
POST /api/select-option
{ "option_index": 0 }

# Decide checkpoint
POST /api/checkpoint/{checkpoint_id}/decide
{ "decision": "approve", "notes": "Optional notes" }

# Get current state
GET /api/state

# Get audit trail
GET /api/audit?format=json|csv

# Export audit trail
GET /api/audit/export?format=json|csv

# Reset session
POST /api/reset
```

## Failure Handling

### Price Changes
- If price increases between `offer verify` and `booking confirm-price`, Checkpoint 2 fires
- Agent never auto-accepts price changes
- Shows original vs. new price with explicit diff

### Payment Failures
- **Retryable errors**: Exponential backoff, up to 3 retries
- **Terminal errors**: Stop immediately, log error
- **Indeterminate errors**: Never retry; mark as indeterminate and halt

### Offer Expiration
- Offers have TTL (typically 15 minutes)
- If expired, agent stops and reports error
- User must start new search

### Seat Unavailability
- Triggers Checkpoint 3 (seat fallback)
- User approves auto-assignment
- Does not block main booking flow

## Project Structure

```
waypoint/
├── src/
│   ├── cli/                    # Atlas CLI wrapper
│   │   ├── wrapper.py          # Subprocess execution
│   │   ├── envelope.py         # JSON envelope parser
│   │   └── errors.py           # Error taxonomy
│   ├── agent/                  # Agent orchestration
│   │   ├── search.py           # Search & ranking engine
│   │   ├── checkpoint.py       # Checkpoint state machine
│   │   ├── audit.py            # Audit trail
│   │   └── reasoning.py        # Qwen integration
│   ├── ui/                     # Web interface
│   │   ├── app.py              # Flask server
│   │   └── templates/          # HTML templates
│   └── parser/                 # Email parser
│       └── email_parser.py     # Cancellation email parser
├── tests/                      # Test suite
├── requirements.txt            # Python dependencies
├── run.py                      # Main entry point
└── README.md                   # This file
```

## Key Design Decisions

1. **Never auto-approve checkpoints** — Always explicit user action
2. **Never retry uncertain payments** — Mark indeterminate and stop
3. **Never persist passenger details** in logs (one-time input only)
4. **Treat all IDs as opaque** — Never parse, reformat, or regenerate
5. **Branch on envelope `code`** — Not HTTP status or exit codes
6. **Sandbox data never drives real decisions** — Clear warning in UI

## Limitations (Current Release)

- **Forward booking only**: Cannot cancel, refund, or change existing bookings
- **Payment**: Atlas balance only (no credit card support)
- **After-sales**: No support for refunds, cancellations, or changes
- **Scope**: Handles replacement booking, not original cancellation

These limitations are explicit in the UX rather than hidden.

## Testing

```bash
# Run tests
python3.12 -m pytest tests/

# Run with coverage
python3.12 -m pytest tests/ --cov=src
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

### Alibaba Cloud ECS (planned)

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

Built with Qoder for the Atlas hackathon. The CLI wrapper, checkpoint state machine, and UI were scaffolded using Qoder's code generation capabilities.
