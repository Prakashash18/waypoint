# What's real in Waypoint

Last verified 2026-08-30 by `tests/api_smoke.py` (39 of 40 checks passing).

## The rule

**No source is simulated.** When a provider is unconfigured, fails, or has
nothing to say, the tool returns no data and states why. Nothing is invented to
fill the gap. Every record carries a `provenance` block naming its source,
status and licence, and the UI shows that on the card.

This was not always true — see [What used to be fake](#what-used-to-be-fake).

## Where each fact comes from

| What you see | Source | Key needed |
|---|---|---|
| Flight fares, times, airlines, seats | Atlas CLI | already configured |
| Booking, price confirmation, ticketing | Atlas CLI | already configured |
| Cheapest travel window across dates | Atlas CLI (`find_date_deals`) | already configured |
| Hotel rates, review scores, photographs | Booking.com via RapidAPI | `RAPIDAPI_KEY` |
| Real hotels, coordinates, official websites | OpenStreetMap (Overpass) | none |
| Nearest airports | OpenStreetMap, then a bundled reference | none |
| Screenshots of hotel websites, map views | Playwright + OpenStreetMap tiles | none |
| Neighbourhood descriptions, geotagged photos | Wikipedia, Wikimedia Commons | none |
| Live flight delays | AviationStack | `AVIATIONSTACK_API_KEY` |
| Your city, currency and timezone | ip-api.com, or the browser | none |
| Voice in and out | ElevenLabs Scribe and Turbo v2.5 | `ELEVENLABS_API_KEY` |
| The planning agent itself | OpenAI | `OPENAI_API_KEY` |

`GET /api/sources` reports which of these are configured right now.

## What each source cannot do

- **OpenStreetMap has no prices.** Hotels from `places.find_hotels` come back
  with `price_per_night: null`. They are real places with real coordinates and
  often an official website; they are not quotes. If rates are unavailable the
  agent says the price is unavailable rather than guessing one.
- **Booking.com rates are quotes, not holds.** We never reserve a room or take
  payment. The button opens the site the rate was quoted on.
- **The bundled airport list is reference data, not a live lookup.** It is used
  only when Overpass fails, and says so: its provenance reads
  `Bundled airport reference`, never `OpenStreetMap`.
- **Currency is never converted.** Prices are quoted in whatever currency the
  provider returned. If two providers answer in different currencies the trip
  shows no combined total and says why — we hold no exchange rates.
- **Flight times are local to their airport.** That is how airlines publish
  them. They are not shifted into your timezone.

## What used to be fake

Two generators produced invented data that was indistinguishable from real
output. Both are deleted; the commits are in git history.

- `hotels_tool._search_simulated()` invented hotel names ("Kuta Beach Inn",
  "Jimbaran Bay Villas") with `random.uniform()` prices, and the RapidAPI path
  fell through to it silently on any error. An unsubscribed key therefore
  rendered as confident hotel cards.
- `flight_status._get_simulated_delays()` did the same for delays on any
  exception, and a `/api/tracker/simulate` toggle switched it on deliberately.

The toggle endpoint is also gone: after the generator was removed it still
returned `{"success": true, "message": "Simulated delays enabled"}` while
changing nothing.

## Checking it yourself

```bash
venv/bin/python tests/api_smoke.py
```

Two of its checks exist specifically to catch a regression to fabrication:

- `OSM hotels carry no fake price` — asserts every price is `None`
- `imagery refuses to fake` — asserts no image is returned when none is real

Ask for something that does not exist and watch it decline:

```bash
curl -s -X POST localhost:2000/api/agent/plan -H 'Content-Type: application/json' \
  -d '{"request":"Find me a hotel in Zzqqxnowhere"}' | python3 -m json.tool
```
