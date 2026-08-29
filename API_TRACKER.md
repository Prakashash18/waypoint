# API Call Tracker & Simulate Toggle

## Two New Features

### 1. API Call Tracker 📊

Real-time tracking of all external API calls with cost monitoring.

**What's Tracked:**
- **OpenAI** — Every GPT-4 call (chat, image analysis, tradeoffs, explanations)
- **Atlas CLI** — Every flight search, offer verification, booking command
- **AviationStack** — Every flight delay API request

**Metrics:**
- Call count per service
- Total cost in USD (based on OpenAI token pricing)
- Token usage (input/output)
- Response time (ms)
- Success/error status

**UI Display:**
- Dark bar at top of page shows live counts
- Auto-refreshes every 5 seconds
- Manual refresh button (🔄)
- Endpoints available at:
  - `GET /api/tracker/summary` — aggregated stats
  - `GET /api/tracker/recent?n=20` — last N calls
  - `GET /api/tracker/export` — full JSON log

**Example:**
```
📊 12 calls  🤖 OpenAI: 8  ✈️ Atlas: 3  📡 AviationStack: 1  💰 $0.045
```

### 2. Simulate Toggle 🎭

Checkbox in the delays panel to switch between real and fake delay data.

**Why?**
- Real AviationStack data may show 0 delays on quiet days (not dramatic for demos)
- Simulated data generates 5-8 fake delayed flights from Changi (SIN) for a compelling demo
- Lets you demonstrate the full booking flow without depending on actual delays

**How:**
- Check "Simulate (demo)" in the delays panel header
- Uncheck to return to real AviationStack data
- Chat notification confirms mode change
- Delays auto-refresh when toggled

**Simulated Data Includes:**
- Realistic airlines (AirAsia, Singapore Airlines, Scoot, etc.)
- Realistic delay times (15-180 minutes)
- Real airport codes (SIN, KUL, etc.)
- Proper flight number format

## Technical Implementation

### Files Modified

**New:**
- `src/agent/api_tracker.py` — Thread-safe singleton tracker with cost calculation

**Modified:**
- `src/agent/reasoning.py` — Added tracking to all OpenAI calls
- `src/agent/flight_status.py` — Added tracking to AviationStack + simulate toggle logic
- `src/cli/wrapper.py` — Added tracking to all Atlas CLI commands
- `src/ui/app.py` — Added 4 new endpoints for tracker and simulate
- `src/ui/templates/index.html` — Added tracker bar UI + simulate checkbox + JS functions

### Architecture

```
User Action (chat, search, etc.)
         ↓
    Service Layer
         ↓
    tracker.record_*()
         ↓
    APICallTracker (singleton)
         ↓
    Flask API (/api/tracker/*)
         ↓
    Frontend JS (refreshTracker)
         ↓
    Tracker Bar UI
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tracker/summary` | GET | Aggregated stats: total calls, cost, breakdown by service |
| `/api/tracker/recent?n=20` | GET | Last N API calls with full details |
| `/api/tracker/export` | GET | Complete JSON log of all calls |
| `/api/tracker/simulate` | POST | Toggle simulated delays: `{"enabled": true}` |

### Cost Calculation

OpenAI pricing (per 1M tokens):
- GPT-4: $30 in / $60 out
- GPT-4 Vision: $30 in / $60 out
- GPT-3.5 Turbo: $0.50 in / $1.50 out

Atlas CLI: Free (local execution)
AviationStack: Free tier (100 req/month)

## Usage Example

1. **Start the app:**
   ```bash
   cd /Users/prakash/Atlas/waypoint
   source venv/bin/activate
   python run.py
   ```

2. **Open UI:** http://localhost:2000

3. **See tracker bar** at top showing 0 calls initially

4. **Chat with agent** — each message increments OpenAI count

5. **Search flights** — each search increments Atlas CLI count

6. **Toggle simulate** — check the box in delays panel to show fake dramatic delays

7. **Watch costs** — see real-time cost accumulation

## Demo Flow

```
1. Open app → tracker shows 0 calls
2. Chat: "My flight from SIN to KUL was cancelled" → OpenAI: 1 call ($0.003)
3. Allow location → AviationStack: 1 call (free)
4. Check "Simulate" → delays panel shows 6 fake delays
5. Chat: "Book me the earliest flight" → OpenAI: 1 call
6. Search flights → Atlas CLI: 1 call
7. Tracker bar updates: 📊 4 calls  💰 $0.006
```

## Notes

- Tracker resets when Flask app restarts (in-memory only)
- For persistent tracking, would need database storage
- Simulate toggle is global (affects all users in same session)
- In production, would want per-user session tracking
