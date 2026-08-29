# Waypoint — Geolocation & Flight Delays Feature

## What's New

Waypoint now includes two powerful features:

1. **📍 Automatic Location Detection** — Detects your device location and finds nearby airports
2. **🚨 Real-Time Flight Delays** — Shows current delays from your nearest airport for the next 3 days

## How It Works

### Geolocation Flow

1. **Page loads** → Browser requests location permission
2. **User approves** → Device coordinates captured
3. **Find nearby airports** → Matches coordinates to airport database
4. **Display banner** → Shows nearest airport with distance
5. **Auto-fetch delays** → Pulls delay information automatically

### Flight Delay Data

- **Real API** (optional): AviationStack API for live data
- **Demo Mode** (default): Simulated realistic delays for demonstration
- **Coverage**: Next 3 days, 5-10 delayed flights per day
- **Details**: Flight number, airline, route, delay duration, gates

## Features

### 📍 Location Banner

When you open Waypoint:
- Browser asks for location permission
- Shows nearest airport with distance
- Click "View Delays" to see current disruptions

**Example:**
```
📍 Kuala Lumpur International
   Kuala Lumpur • KUL • 15.3km away
   [View Delays]
```

### 🚨 Delays Panel

Click "View Delays" to see:
- Total delay count (badge)
- List of delayed flights (up to 10 shown)
- Flight details: airline, number, route
- Delay duration and time changes

**Example:**
```
🚨 Current Delays                    [23 delays]

AirAsia AK742
KUL → SIN  Delayed 45min  08:30 → 09:15

Malaysia Airlines MH318
KUL → BKK  Delayed 120min  10:00 → 12:00
```

## Technical Implementation

### New Files

**`src/agent/flight_status.py`** (262 lines)
- `LocationService` — Geolocation and airport matching
- `FlightStatusService` — Flight delay retrieval
- Airport database with coordinates
- Haversine distance calculation
- AviationStack API integration (optional)
- Simulated delay generation for demo

### API Endpoints

**`POST /api/location`**
```json
Request:
{
  "lat": 3.1390,
  "lon": 101.6869
}

Response:
{
  "success": true,
  "airports": [
    {
      "code": "KUL",
      "name": "Kuala Lumpur International",
      "city": "Kuala Lumpur",
      "distance_km": 15.3
    }
  ],
  "location": {"lat": 3.1390, "lon": 101.6869}
}
```

**`GET /api/flight-delays?airport=KUL&days=3`**
```json
Response:
{
  "success": true,
  "airport": "KUL",
  "delays": [
    {
      "flight_number": "AK742",
      "airline": "AirAsia",
      "departure_airport": "KUL",
      "arrival_airport": "SIN",
      "scheduled_departure": "2026-08-28T08:30:00Z",
      "actual_departure": "2026-08-28T09:15:00Z",
      "delay_minutes": 45,
      "status": "delayed",
      "terminal": "T1",
      "gate": "A12"
    }
  ],
  "count": 23
}
```

### UI Components

**Location Banner**
- Shows detected airport
- Distance from current location
- "View Delays" button

**Delays Panel**
- Toggleable panel
- Delay count badge (red/green)
- Scrollable list of delays
- Color-coded by delay severity

## Airport Database

Built-in database of major airports:

| Code | Name | City |
|------|------|------|
| KUL | Kuala Lumpur International | Kuala Lumpur |
| SIN | Singapore Changi | Singapore |
| BKK | Bangkok Suvarnabhumi | Bangkok |
| HKG | Hong Kong International | Hong Kong |
| NRT | Tokyo Narita | Tokyo |
| ICN | Seoul Incheon | Seoul |
| JFK | New York JFK | New York |
| LAX | Los Angeles International | Los Angeles |
| LHR | London Heathrow | London |
| CDG | Paris Charles de Gaulle | Paris |

## Using Real Flight Data

To get **live flight delays** instead of simulated data:

### Option 1: AviationStack API (Free Tier)

1. Sign up at https://aviationstack.com
2. Get your free API key (100 requests/month)
3. Add to `.env`:
   ```bash
   AVIATIONSTACK_API_KEY=your-api-key-here
   ```
4. Restart the server

**Free tier includes:**
- 100 requests/month
- Historical data (last 30 days)
- Real-time status updates

### Option 2: FlightAware API

1. Sign up at https://flightaware.com/aeroapi
2. Get API key
3. Update `FlightStatusService` to use FlightAware endpoint

### Option 3: OpenSky Network (Free)

1. No API key required
2. Open source flight data
3. Update service to use OpenSky API

## Usage Examples

### Example 1: Auto-Detection

```
[Page loads]
Browser: "Allow location access?"
User: Allow

[Banner appears]
📍 Kuala Lumpur International
   Kuala Lumpur • KUL • 15.3km away
   [View Delays]

User clicks "View Delays"

[Panel shows]
🚨 Current Delays                    [23 delays]

AirAsia AK742
KUL → SIN  Delayed 45min  08:30 → 09:15

[... more delays ...]

User: "My flight AK742 is delayed! Can you help me rebook?"
Agent: "I see AK742 is delayed by 45 minutes. Let me find you 
        alternative flights..."
```

### Example 2: Conversational Integration

```
User: "My flight from KUL to SIN is delayed. What are my options?"

Agent: "I can see there are quite a few delays from KUL today. 
        Let me search for replacement flights for you.
        
        Based on your location, I found these options..."
        
[Shows ranked options]
```

### Example 3: Proactive Alerts

```
[Future enhancement]

Agent: "I noticed your flight AK742 from KUL is now delayed by 
        45 minutes. Would you like me to search for earlier 
        alternatives?"

User: "Yes please!"

[Agent searches and shows options]
```

## Configuration

### Environment Variables

Add to `.env`:

```bash
# Optional: Real flight data
AVIATIONSTACK_API_KEY=your-key-here

# Optional: Custom delay simulation
DELAY_SIMULATION_MODE=realistic|random|minimal
```

### Browser Permissions

The browser will ask for location permission. You can:
- **Allow** — Enables automatic airport detection
- **Deny** — Falls back to manual airport selection
- **Remember choice** — Won't ask again

## Privacy & Security

- **Location data**: Only used to find nearby airports, not stored
- **Coordinates**: Sent to backend only when page loads
- **No tracking**: Location not logged or persisted
- **IP geolocation fallback**: Available if GPS denied

## Performance

- **Location detection**: ~1-2 seconds
- **Airport matching**: Instant (local database)
- **Delay fetching**: ~2-3 seconds (API call)
- **Simulated delays**: Instant (generated locally)

## Limitations

### Current

- Airport database limited to 10 major airports
- Simulated delays are not real (demo mode)
- Requires HTTPS for geolocation (browser requirement)
- Free AviationStack tier: 100 requests/month

### Future Enhancements

- Expand airport database to all IATA codes
- Add more flight status APIs
- Real-time push notifications for delay changes
- Historical delay patterns
- Predictive delay alerts
- Integration with airline apps

## Testing

### Test Geolocation

1. Open http://localhost:2000
2. Allow location permission
3. Verify banner shows nearest airport
4. Click "View Delays"
5. Verify delay list appears

### Test Without Location

1. Open in incognito/private mode
2. Deny location permission
3. App should still work (manual mode)

### Test API Endpoints

```bash
# Test location
curl -X POST http://localhost:2000/api/location \
  -H "Content-Type: application/json" \
  -d '{"lat": 3.1390, "lon": 101.6869}'

# Test delays
curl http://localhost:2000/api/flight-delays?airport=KUL&days=3
```

## Demo Script

For the perfect demo:

1. **Open app** (10s)
   - Show location permission prompt
   - Allow access
   - Banner appears with nearest airport

2. **Show delays** (20s)
   - Click "View Delays"
   - Scroll through delay list
   - Point out delay count and details

3. **Start conversation** (30s)
   - "My flight AK742 is delayed, help me rebook"
   - Agent acknowledges delay
   - Shows replacement options

4. **Complete booking** (2 min)
   - Select option
   - Approve checkpoints
   - Ticket issued

**Hero shot**: Automatic location detection → delays appear → conversational rebooking

## Cost

- **Geolocation**: Free (browser API)
- **Simulated delays**: Free
- **AviationStack free tier**: $0 (100 req/month)
- **AviationStack paid**: $49/month (10,000 req)
- **FlightAware**: $0.01/request

## Next Steps

1. Restart the server to load new features
2. Open in browser and allow location
3. View delays from your nearest airport
4. Start a conversation about a delayed flight
5. Complete the rebooking flow

Enjoy location-aware, delay-informed rebooking! 🚀
