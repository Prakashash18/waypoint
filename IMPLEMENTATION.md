# Waypoint — Implementation Summary

## What Was Built

A complete disruption rebooking agent for stranded air travelers with:

### 1. CLI Wrapper Layer (`src/cli/`)
- **wrapper.py**: Subprocess execution for atlas-flight commands with timeout handling
- **envelope.py**: JSON envelope parser for standard Atlas responses
- **errors.py**: Comprehensive error taxonomy with retry logic
  - Retryable vs terminal errors
  - Special handling for price changes, payment indeterminate states
  - Exponential backoff strategy

### 2. Agent Orchestration (`src/agent/`)
- **search.py**: Search and ranking engine
  - Ranks flights against traveler constraints (deadline, price, availability)
  - Composite scoring algorithm
  - Tradeoff generation for each option
  
- **checkpoint.py**: Four mandatory approval checkpoints
  1. Initial booking authorization
  2. Price change acceptance
  3. Seat fallback selection
  4. Final payment summary
  
  Each checkpoint shows:
  - What permission is being requested
  - Agent's reasoning
  - What changed since last checkpoint
  - Exact CLI command to execute
  - Approve/Reject/Ask Question options
  
- **audit.py**: Append-only audit trail
  - Timestamps all events
  - Tracks request_ids
  - Exportable as JSON or CSV
  - Complete decision history
  
- **reasoning.py**: Qwen integration (via Alibaba Cloud Model Studio)
  - Generates human-readable tradeoffs
  - Explains checkpoint decisions
  - Parses cancellation emails
  - Falls back to templates if API unavailable

### 3. Web UI (`src/ui/`)
- **app.py**: Flask web server
  - RESTful API endpoints
  - Real-time state updates
  - Session management
  
- **templates/index.html**: Single-page application
  - Disruption intake form
  - Ranked options display with tradeoffs
  - Checkpoint decision cards
  - Audit trail viewer
  - Success/completion screen

### 4. Email Parser (`src/parser/`)
- **email_parser.py**: Cancellation email parser
  - AI-powered extraction via Qwen
  - Regex fallback for common patterns
  - PNR-style JSON input support

### 5. Entry Points
- **run.py**: Web UI server (Flask on port 5000)
- **demo.py**: CLI demonstration script
  - Shows complete end-to-end flow
  - Perfect for screen recording
  - No web UI required

### 6. Documentation
- **README.md**: Complete documentation
  - Architecture overview
  - Installation guide
  - API reference
  - Failure handling
  - Deployment instructions
- **.env.example**: Environment configuration template
- **setup.sh**: Automated setup script

## Key Features

### Trust-First Design
- Never auto-approves checkpoints
- Explicit user confirmation at every decision point
- Transparent reasoning at each step
- Complete audit trail

### Robust Error Handling
- Price change detection and re-confirmation
- Payment indeterminate state handling (never retry uncertain payments)
- Offer expiration detection
- Seat unavailability fallback
- Retryable vs terminal error classification

### Production-Ready
- Sandbox environment for development
- No passenger data persistence in logs
- Opaque ID handling (never parse/regenerate)
- Exportable audit trail for compliance

## File Structure

```
waypoint/
├── src/
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── wrapper.py          (184 lines)
│   │   ├── envelope.py         (81 lines)
│   │   └── errors.py           (234 lines)
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── search.py           (215 lines)
│   │   ├── checkpoint.py       (575 lines)
│   │   ├── audit.py            (326 lines)
│   │   └── reasoning.py        (257 lines)
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── app.py              (207 lines)
│   │   └── templates/
│   │       └── index.html      (679 lines)
│   └── parser/
│       ├── __init__.py
│       └── email_parser.py     (143 lines)
├── tests/
├── venv/                       (Python 3.12 virtual environment)
├── requirements.txt
├── .env.example
├── setup.sh
├── run.py
├── demo.py
└── README.md

Total: ~3,100 lines of production code
```

## Technology Stack

- **Python 3.12**: Core language (required by atlas-flight-booking)
- **atlas-flight CLI**: Apache-2.0 flight booking CLI
- **Flask**: Web framework
- **Qwen**: Alibaba Cloud Model Studio for reasoning
- **Sandbox**: Development environment

## Usage

### Quick Start

```bash
# 1. Setup
cd waypoint
./setup.sh

# 2. Authenticate
export PATH="$HOME/.local/bin:$PATH"
atlas-flight auth login
# Open the URL in browser, then:
atlas-flight auth poll

# 3. Run Web UI
source venv/bin/activate
python run.py
# Open http://localhost:5000

# 4. Or run CLI demo
source venv/bin/activate
python demo.py
```

### Demo Scenario

The system handles a complete disruption flow:
1. KUL → SIN flight cancelled
2. Original departure: tomorrow 8am
3. Hard deadline: must arrive before 1pm
4. Agent searches, ranks 5 options
5. User selects best option
6. Four checkpoints fire in sequence
7. Ticket issued
8. Audit trail exported

## What Makes This Special

### 1. Checkpoint Ledger
The core innovation. Every checkpoint is a decision card showing:
- **What**: The permission being requested
- **Why**: Agent's reasoning
- **Changed**: What's different since last checkpoint
- **How**: Exact CLI command
- **Decision**: Approve/Reject/Question

### 2. Audit Trail
Append-only log with:
- Timestamps for every event
- Request IDs for traceability
- CLI commands executed
- Checkpoint decisions with reasoning
- Exportable for compliance

### 3. Failure Handling
Built to handle real-world edge cases:
- Price changes mid-booking
- Offer expiration
- Seat unavailability
- Payment indeterminate states
- Network timeouts

### 4. Trust Through Transparency
- No black boxes
- Every decision explained
- Every change surfaced
- Every action auditable

## Next Steps for Production

1. **Authentication**: Integrate with corporate SSO
2. **Session Management**: Use proper session storage (Redis)
3. **User Input**: Add passenger details form
4. **Notifications**: Email/SMS on booking completion
5. **Multi-passenger**: Handle group bookings
6. **Payment Methods**: Support beyond Atlas balance
7. **After-sales**: Cancellation, changes, refunds
8. **Monitoring**: Error tracking, performance metrics

## Qoder Usage

Qoder was used throughout development for:
- Scaffolding the CLI wrapper layer
- Designing the checkpoint state machine
- Building the audit trail system
- Creating the web UI
- Generating documentation

Approximately 80% of the code was generated or assisted by Qoder, exceeding the hackathon's 20% Qoder usage scoring criterion.

## Hackathon Deliverables Checklist

✅ Working end-to-end run in sandbox  
✅ Cancellation handling (forward booking only)  
✅ Ranked options with tradeoffs  
✅ Four approval checkpoint cards  
✅ Ticket issuance  
✅ Exportable audit trail  
✅ Price change checkpoint firing mid-booking  
✅ Failure handling (price changes, seat unavailability)  
✅ Clean code structure  
✅ Complete documentation  
✅ Qoder usage documented  

## Demo Recording Tips

For the perfect 3-minute screen recording:

1. **Opening (30s)**: Show the web UI, explain disruption scenario
2. **Search (30s)**: Submit disruption, show ranked options with tradeoffs
3. **Select (15s)**: Click best option
4. **Checkpoint 1 (30s)**: Show initial booking card, approve
5. **Checkpoint 2 (45s)**: **THE HERO SHOT** — Price change fires, agent stops, show the card, approve
6. **Checkpoints 3-4 (30s)**: Quick approve seat and payment
7. **Success (15s)**: Show ticket issued
8. **Audit (15s)**: Export audit trail, show JSON

**Key shot**: The price change checkpoint firing mid-booking demonstrates the trust-first design.

## Known Limitations (By Design)

- Forward booking only (no cancellations/changes)
- Atlas balance payment only
- No after-sales operations
- Explicit in UX, not hidden

These limitations are clearly communicated to users rather than obscured.

---

**Built with Qoder for the Atlas Hackathon**  
**Total development time**: ~4 hours  
**Lines of code**: ~3,100  
**Qoder-generated**: ~80%
