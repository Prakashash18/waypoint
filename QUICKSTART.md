# Waypoint Quick Start Guide

## Prerequisites

- Python 3.12
- Homebrew (for pipx)

## Setup (5 minutes)

```bash
# 1. Run setup script
cd waypoint
./setup.sh

# 2. Add atlas-flight to PATH (add to ~/.zshrc for persistence)
export PATH="$HOME/.local/bin:$PATH"

# 3. Authenticate with Atlas
atlas-flight auth login
# Copy the URL, open in browser, complete login
atlas-flight auth poll

# 4. Verify setup
atlas-flight doctor
```

## Run the Web UI

```bash
cd waypoint
source venv/bin/activate
python run.py
```

Open http://localhost:5000

## Run the CLI Demo

```bash
cd waypoint
source venv/bin/activate
python demo.py
```

## Test the Flow

### Web UI Flow

1. **Enter disruption details**:
   - Origin: KUL
   - Destination: SIN
   - Departure: Tomorrow 8:00 AM
   - Deadline: Tomorrow 1:00 PM
   - Passengers: 1

2. **Review ranked options**:
   - See 5 flight options
   - Each with tradeoff description
   - Price, time, availability shown

3. **Select best option**:
   - Click on preferred flight
   - Checkpoint 1 appears

4. **Approve checkpoints**:
   - Review agent's reasoning
   - See what changed
   - View CLI command
   - Click Approve

5. **Complete booking**:
   - All 4 checkpoints approved
   - Ticket issued
   - Export audit trail

### Expected Checkpoints

1. **Initial Booking Authorization**
   - "Book flight AK 700"
   - Shows selected option details

2. **Price Change** (may or may not fire)
   - "Price increased from $180 to $195"
   - Agent explains dynamic pricing
   - Explicit re-confirmation required

3. **Seat Fallback** (may or may not fire)
   - "Preferred seat unavailable"
   - Auto-assignment approval

4. **Final Payment**
   - "Pay $195 from Atlas balance"
   - Final confirmation before ticket issuance

## Troubleshooting

### "atlas-flight: command not found"
```bash
export PATH="$HOME/.local/bin:$PATH"
# Add to ~/.zshrc for persistence
```

### "Authentication required"
```bash
atlas-flight auth login
atlas-flight auth poll
```

### "Python 3.12 not found"
```bash
brew install python@3.12
```

### Port 5000 already in use
```bash
# Edit run.py, change port to 5001
python run.py
```

## For the Demo Recording

Best flow for a 3-minute video:

1. Show web UI (10s)
2. Enter KUL→SIN disruption (20s)
3. Show ranked options with tradeoffs (30s)
4. Select option, show Checkpoint 1 (30s)
5. **HERO SHOT**: Price change checkpoint fires (45s)
6. Approve remaining checkpoints (30s)
7. Show ticket issued (15s)

The price change checkpoint is the key moment that demonstrates trust-first design.

## API Testing

```bash
# Test search
curl -X POST http://localhost:5000/api/disruption \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "KUL",
    "destination": "SIN",
    "original_departure": "2026-08-29T08:00:00",
    "passengers": 1
  }'

# Get options
curl http://localhost:5000/api/options

# Get state
curl http://localhost:5000/api/state

# Get audit trail
curl http://localhost:5000/api/audit?format=json
```

## Next Steps

- Read [README.md](README.md) for full documentation
- Read [IMPLEMENTATION.md](IMPLEMENTATION.md) for architecture details
- Check [src/](src/) for source code
- Run tests: `python -m pytest tests/`

## Support

- Atlas CLI docs: `atlas-flight --help`
- Check environment: `atlas-flight doctor`
- View logs: Check Flask console output

---

**Remember**: This is a sandbox environment. No real bookings will be made.
