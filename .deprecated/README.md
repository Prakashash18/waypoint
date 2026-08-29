# Deprecated tools

**hotels_tool.py.bak** — removed 2026-08-29. Its `_search_simulated()` invented
hotel names ("Kuta Beach Inn", "Jimbaran Bay Villas") with `random.uniform()`
prices, and `_search_via_rapidapi()` silently fell back to it on any provider
error. A 403 therefore rendered as a confident hotel card. Replaced by
`hotel_rates_tool.py` (real rates, honest failure) and `places_tool.py`
(real hotels from OpenStreetMap).

**amadeus_hotels_tool.py.bak** — removed 2026-08-29. Targets the Amadeus
Self-Service API, decommissioned 2026-07-17; `test.api.amadeus.com` no longer
resolves. It also fell back to the simulated generator above.
