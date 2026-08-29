# Waypoint — Agentic Travel Planner
## Build Specification for Expert Developer

---

## Vision

Waypoint is an **AI-powered travel planning agent** with a persistent chat sidebar. Users can:
- **Plan trips** — flights + hotels + activities, composed into packages
- **Explore destinations** — browse hotels, flights, attractions on dedicated pages
- **Chat with the agent** — ask questions, refine searches, get recommendations, book
- **Handle disruptions** — detect delayed/cancelled flights and auto-suggest rebookings

The chat is always visible. The agent is always present. But the main content area has real pages with real data — not just a single chat window.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (SPA)                     │
│                                                       │
│  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  Chat Sidebar │  │        Main Content Area       │  │
│  │  (always on)  │  │                                │  │
│  │               │  │  Pages:                        │  │
│  │  • Messages   │  │  • Home / Trip Planner         │  │
│  │  • Quick      │  │  • Explore (hotels, flights)   │  │
│  │    actions    │  │  • Trip Results (packages)     │  │
│  │  • Voice      │  │  • Booking Flow (checkpoints)  │  │
│  │  • Image      │  │  • My Trips (monitoring)       │  │
│  │    upload     │  │                                │  │
│  └──────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                          │
                     Flask API Layer
                          │
┌─────────────────────────────────────────────────────┐
│                   Tool Registry                       │
│                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ AtlasTool     │  │ HotelsTool   │  │ Future     │ │
│  │ (flights)    │  │ (hotels)     │  │ tools...   │ │
│  │ search       │  │ search       │  │ activities │ │
│  │ book         │  │ book         │  │ weather    │ │
│  │ verify       │  │ reviews      │  │ transfers  │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
│                                                       │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │ FlightStatus │  │ TripComposer │                  │
│  │ (delays)     │  │ (agent brain)│                  │
│  └──────────────┘  └──────────────┘                  │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.12, Flask 3.0 | Already set up |
| Frontend | **React or Next.js** | Move from server-rendered HTML to SPA |
| Flight Search + Booking | Atlas CLI (`atlas-flight-booking`) | Real LCC flight data via subprocess |
| Flight Delays | AviationStack API | Real-time delay data (free tier: 100 req/mo) |
| Hotel Search + Booking | **Amadeus Self-Service API** | Real hotel data, free sandbox, OAuth2 |
| AI Reasoning | OpenAI GPT-4 | Tradeoff generation, conversation, package composition |
| State Management | Redux or Zustand | Trip state across pages |
| Styling | Tailwind CSS | Dark cockpit theme (see design tokens below) |

---

## API Integrations (All Must Be Authentic — No Simulated Data)

### 1. Atlas CLI — Flights
- **Install**: `pipx install atlas-flight-booking --python python3.12`
- **Auth**: `atlas-flight auth login` → returns `authorization_url` → user opens in browser → `atlas-flight auth poll` until authenticated
- **Environment**: `atlas-flight environment use sandbox --json` for development
- **Search**: `atlas-flight search --origin KUL --destination SIN --depart 2026-10-14 --adults 2 --json`
- **Response**: JSON envelope with `{schema_version, status, code, data: {offers: [...]}}` — offers include `carrier`, `flight_number`, `departure_time` (YYYYMMDDHHMM), `arrival_time`, `total_price`, `seats_available`
- **Book**: `booking confirm-price`, `booking baggage`, `booking seat`, `order create`, `order pay`
- **Constraint**: 4 mandatory human checkpoints — cannot auto-approve

### 2. AviationStack — Flight Delays
- **API Key**: Set in `.env` as `AVIATIONSTACK_API_KEY`
- **Endpoint**: `GET http://api.aviationstack.com/v1/flights?access_key=KEY&dep_iata=KUL&limit=100`
- **Free tier**: HTTP only, 100 requests/month, no `flight_status` parameter — filter client-side for `status in ('delayed', 'active')` or `delay > 0`
- **Fallback**: If no API key or API fails, clearly label data as "demo data" — never silently fake it

### 3. Amadeus Self-Service — Hotels (PRIMARY — replace simulated hotel data)
- **Signup**: https://developers.amadeus.com/self-service (free)
- **Auth**: OAuth2 client credentials — `POST /v1/security/oauth/2/token` with `client_id` + `client_secret`
- **Search Destination**: `GET /v1/reference-data/locations?keyword=Bali&subType=CITY`
- **Search Hotels**: `GET /v3/shopping/hotel-offers?cityCode=DPS&checkInDate=2026-10-14&checkOutDate=2026-10-17&adults=2`
- **Response**: Hotels with `name`, `rating`, `geoCode`, `roomOffers[]` containing `room` details, `rate` (price, currency, cancellation policy), `bed` type
- **Booking**: `POST /v1/booking/hotel-bookings` with guest details
- **Sandbox**: Free test environment with real availability for partner properties
- **Config**: `AMADEUS_API_KEY` and `AMADEUS_API_SECRET` in `.env`

### 4. OpenAI — Agent Reasoning
- **Model**: GPT-4 for tradeoff generation, package reasoning, conversation
- **Usage**: Generate human-readable explanations of why one package is better than another
- **Config**: `OPENAI_API_KEY` in `.env`
- **Fallback**: Template-based reasoning when no key available

---

## Existing Code to Build On

The following code exists in `/Users/prakash/Atlas/waypoint/` and should be reused:

| File | What It Does | Reuse As-Is |
|------|-------------|-------------|
| `src/cli/wrapper.py` | AtlasCLI subprocess wrapper | ✅ Yes |
| `src/cli/envelope.py` | Atlas JSON envelope parser | ✅ Yes |
| `src/cli/errors.py` | Typed error hierarchy (AtlasError, SearchError, etc.) | ✅ Yes |
| `src/agent/audit.py` | Append-only audit trail | ✅ Yes |
| `src/agent/checkpoint.py` | 4-checkpoint FSM for booking flow | ✅ Yes |
| `src/agent/search.py` | Flight search + offer ranking | ✅ Yes |
| `src/agent/reasoning.py` | OpenAI-powered tradeoff generation | ✅ Yes |
| `src/agent/flight_status.py` | AviationStack delay checker | ✅ Yes |
| `src/agent/api_tracker.py` | API call counter with cost tracking | ✅ Yes |
| `src/tools/base.py` | ToolBase, ToolResult, ToolError, ToolCapability | ✅ Yes |
| `src/tools/registry.py` | ToolRegistry singleton | ✅ Yes |
| `src/tools/atlas_tool.py` | AtlasTool wrapping AtlasCLI | ✅ Yes |
| `src/tools/flight_status_tool.py` | FlightStatusTool wrapping AviationStack | ✅ Yes |
| `src/tools/hotels_tool.py` | HotelsTool (currently RapidAPI + simulated fallback) | **Rewrite** for Amadeus |
| `src/tools/composer.py` | TripComposer — multi-tool agent | ✅ Yes, extend |
| `src/ui/app.py` | Flask endpoints | ✅ Extend with new pages |
| `src/ui/templates/index.html` | Current single-page cockpit UI | **Replace** with multi-page SPA |

---

## Pages Required

### 1. Home / Trip Planner
- Hero section: "Where do you want to go?"
- Trip form: origin, destination, dates, travelers, budget
- Quick suggestions: popular destinations, last-minute deals
- The chat sidebar shows agent greetings and recent activity

### 2. Explore / Search Results
- Left panel: filters (price range, star rating, amenities, airline, departure time)
- Main grid: hotel cards + flight cards interleaved
- Each card has: image, name, rating, price, key amenities
- Click a card → detail panel slides in from right
- Agent chat sidebar: "I found 42 hotels in Bali. The best value is Ubud Village Hotel — $65/night with a pool and 4.5 rating. Want me to build a package?"
- Sort by: price, rating, agent recommendation

### 3. Trip Results (Packages)
- 3 package cards: Budget, Smart Pick, Comfort
- Each shows: flight details, hotel details, total price, budget analysis, reasoning
- "Customize" button → swap flight or hotel individually
- "Book this" button → enters checkpoint flow

### 4. Booking Flow (Checkpoints)
- 4 mandatory human approval steps:
  1. **Confirm flights** — show selected flights, approve/modify/cancel
  2. **Confirm price** — if price changed since search, show old vs new
  3. **Seat fallback** — if preferred seat unavailable, show alternatives
  4. **Final payment** — full summary, confirm payment
- Each step is a card with clear options, not a form
- Agent explains each step in the chat sidebar

### 5. My Trips (Post-Booking)
- List of booked trips with status
- Flight monitoring: real-time delay alerts via AviationStack
- Proactive rebooking: "Your flight is delayed 3 hours. I found 2 alternatives..."
- Trip details: itinerary, hotel confirmation, receipts

---

## Chat Sidebar (Always Visible)

The chat is the agent's persistent presence. It:
- Shows on every page as a collapsible sidebar (320px wide on desktop, full-screen overlay on mobile)
- Displays agent messages as "flight data strips" with runway-orange left border
- Supports: text input, voice input, image upload (boarding pass OCR)
- Context-aware: when user is on Explore page for Bali, agent already knows the destination
- Recommendation engine: agent proactively suggests based on browsing behavior
  - "You've been looking at 5-star hotels in Seminyak. I found a package that includes flights + hotel for $1,200."
  - "Flight AK727 has only 3 seats left at this price. Want to book now?"

---

## Design System

### Theme: "Cockpit Command"
Dark, aviation-inspired. Feels like a pilot's HUD.

### Color Tokens
```css
--cockpit:    #0B1929;     /* Deep navy background */
--panel:      #1A2332;     /* Card/panel background */
--panel-hi:   #243447;     /* Hover state */
--border:     #2A3A4D;     /* Subtle borders */
--hud:        #E2E8F0;     /* Primary text */
--hud-dim:    #8899AA;     /* Secondary text */
--runway:     #FF6A00;     /* Primary accent (runway edge light) */
--runway-hi:  #FF8C33;     /* Hover accent */
--cleared:    #22C55E;     /* Success / available */
--grounded:   #EF4444;     /* Error / unavailable */
--caution:    #F59E0B;     /* Warning / pending */
```

### Typography
- **Display**: Space Grotesk (Google Fonts) — headings, buttons
- **Data**: JetBrains Mono (Google Fonts) — prices, times, flight numbers, IATA codes

### Design Principles
- Agent-first: chat is always visible, not a popup
- Data-dense: show flight numbers, prices, times in monospace
- Touch-friendly: minimum 42px tap targets
- Mobile-first: sidebar collapses to overlay on mobile
- Motion: subtle transitions, `prefers-reduced-motion` support

---

## Agent Intelligence

### Trip Composer (existing in `src/tools/composer.py`)
1. User says "Plan a trip to Bali for 2, budget $1500, Oct 14-17"
2. Agent resolves "Bali" → DPS (IATA code) via `CITY_TO_IATA` mapping
3. Parallel dispatch to tool registry:
   - `atlas_flights.search_flights(KUL, DPS, 2026-10-14, 2)` → real flights
   - `hotels.search_hotels(Bali, 2026-10-14, 2026-10-17, 2)` → real hotels (Amadeus)
4. Compose packages: Budget, Smart Pick, Comfort
5. Rank by: budget compliance, hotel rating, flight timing, seat availability
6. Present in chat + main content area simultaneously

### Proactive Recommendations
- Track user browsing context (which hotels/flights they've viewed)
- Agent suggests: "Based on what you've been looking at, here's a better deal..."
- Agent alerts: "Only 3 seats left on AK727 at this price"
- Agent warns: "Hotel check-in is at 14:00 but your flight arrives at 09:30 — I found a hotel with early check-in"

### Disruption Monitoring (Background)
- After booking, agent monitors flight status via AviationStack
- If delay detected: "Your flight AK727 is delayed 3 hours. I found 2 alternatives..."
- Auto-search alternatives using existing rebooking flow
- Present options in chat with one-click rebooking

---

## Booking Constraints

1. **Four mandatory human checkpoints** — never auto-approve
2. **Atlas CLI only** for flight booking — no direct API
3. **Payment is Atlas-balance-only** — no credit card in current release
4. **No refunds/cancellations after ticketing**
5. **All IDs are opaque strings** — don't parse or assume format
6. **Branch on `code` field**, not HTTP status or exit codes

---

## Environment Setup

```bash
# Clone and setup
cd /Users/prakash/Atlas/waypoint
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Atlas CLI
pipx install atlas-flight-booking --python python3.12
atlas-flight environment use sandbox --json
atlas-flight auth login --json
# Open the authorization_url in browser
atlas-flight auth poll --json
atlas-flight doctor --json

# Environment variables (.env)
OPENAI_API_KEY=sk-...
AVIATIONSTACK_API_KEY=<your-aviationstack-key>
AMADEUS_API_KEY=<your-amadeus-key>
AMADEUS_API_SECRET=<your-amadeus-secret>
FLASK_ENV=development
PORT=2000

# Run
python run.py
```

---

## Deliverables

1. **Multi-page SPA** with React/Next.js + Tailwind, replacing the single-page HTML
2. **Amadeus hotel integration** replacing simulated hotel data (rewrite `src/tools/hotels_tool.py`)
3. **Persistent chat sidebar** on every page, context-aware
4. **Explore page** with filters, grid layout, detail panels
5. **Booking flow** using existing 4-checkpoint FSM
6. **My Trips page** with flight monitoring and proactive rebooking
7. **Recommendation engine** — agent proactively suggests based on browsing
8. **Mobile responsive** — sidebar collapses, touch-friendly, safe area insets
9. **Audit trail integration** — all bookings logged to existing AuditTrail
10. **API call tracker** — existing tracker extended to cover Amadeus calls

---

## Key Files to Study First

1. `src/tools/base.py` — understand the ToolBase interface
2. `src/tools/composer.py` — understand how TripComposer works
3. `src/agent/checkpoint.py` — understand the 4-checkpoint FSM
4. `src/cli/errors.py` — understand the error taxonomy
5. `src/agent/audit.py` — understand the audit trail
6. `src/agent/reasoning.py` — understand how OpenAI generates explanations
