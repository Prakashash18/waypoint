"""
Waypoint UI - Flask web application for conversational rebooking
"""

from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_cors import CORS
import json
import io
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.cli import AtlasCLI
from src.agent.session import sessions
from src.agent import (
    SearchEngine, DisruptedItinerary, RankedOption,
    CheckpointManager, Checkpoint, CheckpointType, CheckpointDecision,
    AuditTrail, AuditEvent, AuditEventType,
    ReasoningEngine,
    LocationService, FlightStatusService,
    tracker
)


import logging
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Global state (for demo purposes - in production, use proper session management)
cli = AtlasCLI()
audit = AuditTrail()
reasoning = ReasoningEngine()
checkpoint_manager = CheckpointManager(cli, audit, reasoning)
current_options = []

# The API key in use is scoped to synthesis only, so /v1/voices returns 401 and
# the roster has to be declared here rather than fetched.
DEFAULT_VOICE_ID = 'EXAVITQu4vr4xnSDxMaL'
VOICE_CHOICES = [
    {'id': 'EXAVITQu4vr4xnSDxMaL', 'name': 'Sarah', 'description': 'warm, calm'},
    {'id': '21m00Tcm4TlvDq8ikWAM', 'name': 'Rachel', 'description': 'clear, neutral'},
    {'id': 'ErXwobaYiN019PkySvjV', 'name': 'Antoni', 'description': 'friendly, male'},
    {'id': 'TxGEqnHWrfWFTfGW9XjX', 'name': 'Josh', 'description': 'deep, male'},
]


@app.route('/api/disruption', methods=['POST'])
def submit_disruption():
    """Submit a disruption and get ranked options"""
    global current_options
    
    try:
        data = request.json
        
        # Parse disruption data
        itinerary = DisruptedItinerary(
            origin=data['origin'],
            destination=data['destination'],
            original_departure=datetime.fromisoformat(data['original_departure'].replace('Z', '+00:00')),
            passengers=data.get('passengers', 1),
            hard_deadline=datetime.fromisoformat(data['hard_deadline'].replace('Z', '+00:00')) if data.get('hard_deadline') else None,
            notes=data.get('notes', '')
        )
        
        # Search for options
        current_options = checkpoint_manager.start_session(itinerary)
        
        return jsonify({
            'success': True,
            'options': [opt.to_dict() for opt in current_options]
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@app.route('/api/options')
def get_options():
    """Get current ranked options"""
    return jsonify({
        'options': [opt.to_dict() for opt in current_options]
    })


@app.route('/api/select-option', methods=['POST'])
def select_option():
    """Select an option and present initial booking checkpoint"""
    try:
        data = request.json
        option_index = data['option_index']
        
        if option_index < 0 or option_index >= len(current_options):
            return jsonify({'success': False, 'error': 'Invalid option index'}), 400
        
        selected = current_options[option_index]
        checkpoint = checkpoint_manager.present_initial_booking_checkpoint(selected)
        
        return jsonify({
            'success': True,
            'checkpoint': checkpoint.to_dict(),
            'state': checkpoint_manager.get_state()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@app.route('/api/checkpoint/<checkpoint_id>/decide', methods=['POST'])
def decide_checkpoint(checkpoint_id):
    """Process a checkpoint decision"""
    try:
        data = request.json
        decision_str = data['decision']
        notes = data.get('notes')
        
        decision = CheckpointDecision(decision_str)
        
        success = checkpoint_manager.decide_checkpoint(checkpoint_id, decision, notes)
        
        response = {
            'success': success,
            'state': checkpoint_manager.get_state()
        }
        
        # If there's a new checkpoint, include it
        if checkpoint_manager.current_checkpoint and checkpoint_manager.current_checkpoint.checkpoint_id != checkpoint_id:
            response['new_checkpoint'] = checkpoint_manager.current_checkpoint.to_dict()
        
        return jsonify(response)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@app.route('/api/state')
def get_state():
    """Get current booking state"""
    return jsonify(checkpoint_manager.get_state())


@app.route('/api/audit')
def get_audit():
    """Get audit trail"""
    format_type = request.args.get('format', 'json')
    
    if format_type == 'json':
        return jsonify({
            'session_id': audit.session_id,
            'event_count': len(audit.events),
            'events': [event.to_dict() for event in audit.events]
        })
    elif format_type == 'csv':
        csv_data = audit.export_csv()
        return send_file(
            io.BytesIO(csv_data.encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'audit_{audit.session_id}.csv'
        )
    else:
        return jsonify({'error': 'Invalid format'}), 400


@app.route('/api/audit/export')
def export_audit():
    """Export audit trail as downloadable file"""
    format_type = request.args.get('format', 'json')
    
    if format_type == 'json':
        json_data = audit.export_json()
        return send_file(
            io.BytesIO(json_data.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'audit_{audit.session_id}.json'
        )
    elif format_type == 'csv':
        csv_data = audit.export_csv()
        return send_file(
            io.BytesIO(csv_data.encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'audit_{audit.session_id}.csv'
        )
    else:
        return jsonify({'error': 'Invalid format'}), 400


@app.route('/api/reset', methods=['POST'])
def reset_session():
    """Reset the session"""
    global cli, audit, reasoning, checkpoint_manager, current_options
    
    cli = AtlasCLI()
    audit = AuditTrail()
    reasoning = ReasoningEngine()
    checkpoint_manager = CheckpointManager(cli, audit, reasoning)
    current_options = []
    
    return jsonify({'success': True})


@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle conversational input"""
    try:
        data = request.json
        user_message = data['message']
        
        # Get AI response
        response = reasoning.chat(user_message)
        
        # Try to extract itinerary details from the message
        extracted = reasoning.parse_cancellation_email(user_message)
        
        result = {
            'response': response,
            'extracted_info': extracted
        }
        
        # If we have enough info, start search
        if extracted.get('origin') and extracted.get('destination'):
            try:
                itinerary = DisruptedItinerary.from_dict(extracted)
                current_options = checkpoint_manager.start_session(itinerary)
                result['options'] = [opt.to_dict() for opt in current_options]
                result['response'] += "\n\nI found some replacement flight options for you. Take a look at the options below and let me know which one works best for you."
            except Exception as e:
                # Not enough info yet, continue conversation
                pass
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'response': f"I'm sorry, I encountered an error: {str(e)}",
            'error': str(e)
        }), 400


@app.route('/api/analyze-image', methods=['POST'])
def analyze_image():
    """Analyze uploaded image"""
    try:
        data = request.json
        image_base64 = data['image']
        
        # Analyze image
        extracted = reasoning.analyze_image(image_base64)
        
        response = "I've analyzed your image."
        
        if extracted.get('pnr'):
            response += f" I found booking reference: {extracted['pnr']}."
        if extracted.get('flight_number'):
            response += f" Flight number: {extracted['flight_number']}."
        if extracted.get('origin') and extracted.get('destination'):
            response += f" Route: {extracted['origin']} to {extracted['destination']}."
        
        result = {
            'response': response,
            'extracted_info': extracted
        }
        
        # If we have enough info, start search
        if extracted.get('origin') and extracted.get('destination') and extracted.get('departure'):
            try:
                itinerary = DisruptedItinerary.from_dict(extracted)
                current_options = checkpoint_manager.start_session(itinerary)
                result['options'] = [opt.to_dict() for opt in current_options]
                result['response'] += "\n\nI found some replacement flight options for you based on the information in your image."
            except Exception as e:
                pass
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'response': f"I couldn't analyze the image: {str(e)}",
            'error': str(e)
        }), 400


@app.route('/api/location', methods=['POST'])
def get_location():
    """Get nearby airports based on coordinates"""
    try:
        data = request.json
        lat = data.get('lat')
        lon = data.get('lon')
        
        if lat is None or lon is None:
            return jsonify({'error': 'Latitude and longitude required'}), 400
        
        # Uses OpenStreetMap rather than the old ten-airport table, which
        # returned nothing for most of the world.
        from src.tools import tool_registry
        result = tool_registry.execute('places', 'nearest_airports',
                                       {'lat': lat, 'lon': lon, 'limit': 5})
        nearby = result.data.get('airports', []) if result.is_success() else []

        return jsonify({
            'success': True,
            'airports': nearby,
            'location': {'lat': lat, 'lon': lon},
            'message': result.message,
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/locale', methods=['GET', 'POST'])
def detect_locale():
    """Where the traveller is, and the currency and clock to use.

    POST browser coordinates and timezone for precision; with no body it falls
    back to IP. Also returns the airports they could realistically fly from,
    so nothing downstream has to assume a home hub.
    """
    from src.tools import tool_registry

    data = request.json if request.method == 'POST' and request.is_json else {}
    params = {k: (data or {}).get(k) for k in ('lat', 'lon', 'timezone')}
    params = {k: v for k, v in params.items() if v is not None}

    result = tool_registry.execute('locale', 'detect_locale', params)
    locale = result.data if isinstance(result.data, dict) else {}

    airports = []
    if locale.get('lat') is not None and locale.get('lon') is not None:
        try:
            near = tool_registry.execute('places', 'nearest_airports', {
                'lat': locale['lat'], 'lon': locale['lon'], 'limit': 4})
            if near.is_success():
                airports = near.data.get('airports', [])
        except Exception:
            app.logger.warning('Nearest-airport lookup failed', exc_info=True)

    return jsonify({
        'success': result.is_success(),
        'locale': locale,
        'airports': airports,
        'origin_airport': airports[0] if airports else None,
        'message': result.message,
    })


@app.route('/api/flight-delays', methods=['GET'])
def get_flight_delays():
    """Get delayed flights from an airport"""
    try:
        airport_code = request.args.get('airport', '').upper()
        days = int(request.args.get('days', 3))
        
        if not airport_code:
            return jsonify({'error': 'Airport code required'}), 400
        
        # Get flight delays
        flight_service = FlightStatusService()
        delays = flight_service.get_delays_from_airport(airport_code, days)
        
        return jsonify({
            'success': True,
            'airport': airport_code,
            'delays': delays,
            'count': len(delays)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ── Rebook-from-Delay Endpoints ──────────────────────────────────

@app.route('/api/rebook-start', methods=['POST'])
def rebook_start():
    """Start rebooking flow from a selected delayed flight.
    
    Returns structured questions with predefined options so the user
    can click buttons instead of typing free text.
    """
    try:
        data = request.json
        flight = data.get('flight', {})
        
        origin = flight.get('departure_airport', '')
        destination = flight.get('arrival_airport', '')
        airline = flight.get('airline', '')
        flight_number = flight.get('flight_number', '')
        scheduled = flight.get('scheduled_departure', '')
        delay_minutes = flight.get('delay_minutes', 0)
        
        # Build structured questions
        questions = [
            {
                'id': 'passengers',
                'question': 'How many passengers?',
                'type': 'buttons',
                'options': [
                    {'value': '1', 'label': '1 passenger'},
                    {'value': '2', 'label': '2 passengers'},
                    {'value': '3', 'label': '3 passengers'},
                    {'value': '4', 'label': '4+ passengers'},
                ],
                'default': '1'
            },
            {
                'id': 'deadline',
                'question': 'Do you have a hard deadline (e.g. meeting, connection)?',
                'type': 'buttons',
                'options': [
                    {'value': 'none', 'label': 'No deadline — any time works'},
                    {'value': '4h', 'label': 'Must arrive within 4 hours'},
                    {'value': '8h', 'label': 'Must arrive within 8 hours'},
                    {'value': 'same_day', 'label': 'Must arrive same day'},
                ],
                'default': 'none'
            },
            {
                'id': 'cabin_class',
                'question': 'Preferred cabin class?',
                'type': 'buttons',
                'options': [
                    {'value': 'economy', 'label': 'Economy'},
                    {'value': 'premium', 'label': 'Premium Economy'},
                    {'value': 'business', 'label': 'Business'},
                    {'value': 'any', 'label': 'Any — cheapest is fine'},
                ],
                'default': 'any'
            },
            {
                'id': 'baggage',
                'question': 'Do you need checked baggage?',
                'type': 'buttons',
                'options': [
                    {'value': 'no', 'label': 'Carry-on only'},
                    {'value': 'yes', 'label': 'Yes, checked bags needed'},
                ],
                'default': 'no'
            }
        ]
        
        summary = (
            f"I see your {airline} flight {flight_number} from {origin} to {destination} "
            f"is delayed by {delay_minutes} minutes. Let me find you a replacement."
        )
        
        return jsonify({
            'success': True,
            'summary': summary,
            'flight': flight,
            'questions': questions
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/rebook-confirm', methods=['POST'])
def rebook_confirm():
    """Confirm rebooking with answers from structured questions.
    
    Creates a DisruptedItinerary from the selected flight + user answers,
    then searches Atlas CLI for replacement options.
    """
    global current_options
    
    try:
        data = request.json
        flight = data.get('flight', {})
        answers = data.get('answers', {})
        
        origin = flight.get('departure_airport', '')
        destination = flight.get('arrival_airport', '')
        scheduled = flight.get('scheduled_departure', '')
        
        # Parse answers
        passengers = int(answers.get('passengers', '1').replace('+', ''))
        deadline_val = answers.get('deadline', 'none')
        
        # Parse scheduled departure time
        from datetime import timedelta
        try:
            original_dep = datetime.fromisoformat(scheduled.replace('Z', '+00:00'))
        except Exception:
            original_dep = datetime.utcnow()
        
        # Calculate hard deadline from answer
        hard_deadline = None
        if deadline_val == '4h':
            hard_deadline = original_dep + timedelta(hours=4)
        elif deadline_val == '8h':
            hard_deadline = original_dep + timedelta(hours=8)
        elif deadline_val == 'same_day':
            hard_deadline = original_dep.replace(hour=23, minute=59)
        
        # Build itinerary
        airline = flight.get('airline', '')
        flight_number = flight.get('flight_number', '')
        notes = (
            f"Disrupted flight: {airline} {flight_number} "
            f"from {origin} to {destination}, "
            f"delayed {flight.get('delay_minutes', 0)}min. "
            f"Cabin: {answers.get('cabin_class', 'any')}. "
            f"Baggage: {answers.get('baggage', 'no')}."
        )
        
        itinerary = DisruptedItinerary(
            origin=origin,
            destination=destination,
            original_departure=original_dep,
            passengers=passengers,
            hard_deadline=hard_deadline,
            notes=notes
        )
        
        # Start search
        try:
            current_options = checkpoint_manager.start_session(itinerary)
        except Exception as search_err:
            # Search failed — return helpful message instead of crashing
            tomorrow = (original_dep + timedelta(days=1)).strftime('%Y-%m-%d')
            return jsonify({
                'success': True,
                'response': (
                    f"I searched for flights from {origin} to {destination} "
                    f"on {original_dep.strftime('%Y-%m-%d')} but couldn't find "
                    f"any available seats.\n\n"
                    f"This can happen when:\n"
                    f"- The route has limited availability in our booking system\n"
                    f"- The date is too close to today\n\n"
                    f"Try selecting a different flight from the delays panel, "
                    f"or tell me a different route and I'll search again."
                ),
                'options': [],
                'search_failed': True
            })
        
        response_text = f"Searching for flights from {origin} to {destination}"
        if hard_deadline:
            response_text += f" (must arrive by {hard_deadline.strftime('%H:%M')})"
        response_text += "..."
        
        result = {
            'success': True,
            'response': response_text,
            'options': [opt.to_dict() for opt in current_options] if current_options else []
        }
        
        if current_options:
            result['response'] += (
                f"\n\nI found {len(current_options)} replacement options. "
                f"Here they are ranked by best value:"
            )
        else:
            result['response'] += (
                "\n\nSorry, I couldn't find any available flights right now. "
                "Would you like me to try a different date?"
            )
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'response': f"I ran into a problem: {str(e)}",
            'error': str(e)
        }), 400


# ── API Call Tracker Endpoints ───────────────────────────────────

@app.route('/api/tracker/summary', methods=['GET'])
def get_tracker_summary():
    """Get summary of all API calls"""
    return jsonify(tracker.summary())


@app.route('/api/tracker/recent', methods=['GET'])
def get_recent_calls():
    """Get the N most recent API calls"""
    n = request.args.get('n', 20, type=int)
    return jsonify({'calls': tracker.recent(n)})


@app.route('/api/tracker/export', methods=['GET'])
def export_tracker_log():
    """Export full API call log as JSON"""
    return jsonify(json.loads(tracker.export_json()))


@app.route('/api/tools', methods=['GET'])
def list_tools():
    """List all registered tools and their capabilities"""
    from src.tools import tool_registry
    return jsonify(tool_registry.to_dict())


@app.route('/api/plan-trip', methods=['POST'])
def plan_trip():
    """Plan a trip. Structured params in, agent-planned itinerary out.

    Kept for the existing UI. The fixed flight+hotel pipeline behind it was
    replaced by TripAgent, which chooses its own tools, so results now vary
    with what was actually asked for.
    """
    try:
        data = request.json or {}
        brief = _brief_from_params(data)
        result = _agent().plan(brief, context=data)
        return jsonify({
            'success': True,
            'packages': _packages_from(result),
            'trip': _trip_from(result),
            'combos': _combos_from(result),
            'cards': _cards_from(result, _snapshot(None)),
            'response': result['answer'],
            **result,
        })
    except Exception as e:
        app.logger.exception('plan-trip failed')
        return jsonify({
            'success': False,
            'response': f"I ran into a problem planning your trip: {e}",
            'error': str(e),
        }), 400


@app.route('/api/agent/plan', methods=['POST'])
def agent_plan():
    """Plan from a free-form request: {"request": "...", "context": {...}}."""
    try:
        data = request.json or {}
        brief = (data.get('request') or '').strip()
        if not brief:
            return jsonify({'success': False,
                            'error': 'request is required'}), 400
        session = sessions.get_or_create(data.get('session_id'), data.get('user_id'))
        before = _snapshot(session)
        result = _agent().plan(brief, context=data.get('context'), session=session)
        return jsonify({'success': True, 'packages': _packages_from(result),
                        'trip': _trip_from(result),
                        'combos': _combos_from(result),
                        'cards': _cards_from(result, before),
                        'follow_ups': _follow_ups(result), **result})
    except Exception as e:
        app.logger.exception('agent plan failed')
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/agent/stream', methods=['POST'])
def agent_stream():
    """Plan a trip, emitting each tool call the moment it happens.

    The previous version ran the whole plan and only then yielded the steps it
    had collected, so nothing reached the browser until the work was already
    finished — a streaming endpoint that did not stream. The planner now runs on
    its own thread and pushes steps through a queue as they occur.
    """
    import queue as _queue
    import threading

    data = request.json or {}
    brief = (data.get('request') or _brief_from_params(data)).strip()
    context = data.get('context') or data
    session = sessions.get_or_create(data.get('session_id'), data.get('user_id'))
    before = _snapshot(session)

    events: "_queue.Queue" = _queue.Queue()
    DONE = object()

    def work():
        try:
            result = _agent().plan(
                brief, context=context, session=session,
                on_step=lambda step: events.put(('step', step.to_dict())))
            events.put(('done', {'packages': _packages_from(result),
                                 'trip': _trip_from(result),
                                 'combos': _combos_from(result),
                                 'cards': _cards_from(result, before),
                                 'follow_ups': _follow_ups(result), **result}))
        except Exception as exc:
            app.logger.exception('agent stream failed')
            events.put(('error', {'error': str(exc)}))
        finally:
            events.put((DONE, None))

    threading.Thread(target=work, daemon=True).start()

    def generate():
        # Open immediately so the browser starts rendering rather than waiting
        # on the first tool call, which can be a second or two away. The id goes
        # out first so the client can interrupt this very run.
        yield f"event: open\ndata: {json.dumps({'session_id': session.id})}\n\n"
        while True:
            try:
                kind, payload = events.get(timeout=20)
            except _queue.Empty:
                yield ': keepalive\n\n'   # hold the connection through a slow call
                continue
            if kind is DONE:
                break
            yield f"event: {kind}\ndata: {json.dumps(payload, default=str)}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'Connection': 'keep-alive',
                             'X-Accel-Buffering': 'no'})


@app.route('/api/agent/cancel', methods=['POST'])
def agent_cancel():
    """Interrupt a run in progress.

    The agent checks between steps, so an in-flight upstream call finishes
    first — stopping takes a second or two rather than being instant. Whatever
    was already found is kept.
    """
    data = request.json or {}
    session = sessions.get((data.get('session_id') or '').strip())
    if session is None:
        return jsonify({'success': False, 'error': 'no such session'}), 404
    was_running = session.running
    session.cancel()
    return jsonify({'success': True, 'was_running': was_running,
                    'session_id': session.id})


@app.route('/api/session/<session_id>', methods=['GET', 'DELETE'])
def session_state(session_id):
    """What the agent remembers, or forget it."""
    if request.method == 'DELETE':
        sessions.drop(session_id)
        return jsonify({'success': True, 'forgotten': session_id})

    session = sessions.get(session_id)
    if session is None:
        return jsonify({'success': False, 'error': 'no such session'}), 404
    return jsonify({'success': True, **session.summary()})


@app.route('/api/session/<session_id>/preferences', methods=['POST'])
def session_preferences(session_id):
    """Record preferences the traveller states about themselves."""
    session = sessions.get_or_create(session_id)
    session.remember(**(request.json or {}))
    return jsonify({'success': True, 'preferences': session.preferences})


@app.route('/api/settings/cache', methods=['GET', 'DELETE'])
def cache_settings():
    """Hotel-rate cache: what is held, what today has cost, and a reset.

    The provider's free tier is metered, so this is shown rather than hidden:
    a traveller can see how many live lookups remain and clear the cache
    deliberately when they want fresh prices.
    """
    from src.tools import tool_registry
    rates = tool_registry.get('hotel_rates')
    if rates is None or not hasattr(rates, 'cache_stats'):
        return jsonify({'success': False, 'error': 'no rate provider'}), 404

    # Upgrading a plan changes the allowance behind our back, so offer a way
    # to forget what we think it is.
    if request.args.get('recheck') and hasattr(rates, 'recheck_quota'):
        rates.recheck_quota()
        return jsonify({'success': True, **rates.cache_stats(),
                        'note': 'Allowance forgotten; the next search re-reads it.'})

    if request.method == 'DELETE':
        return jsonify({'success': True, **rates.clear_cache(),
                        'note': 'Cleared. The next search fetches fresh prices '
                                'and spends from today\'s allowance.'})

    return jsonify({'success': True, **rates.cache_stats()})


@app.route('/api/sources', methods=['GET'])
def list_sources():
    """Which data providers are configured, so the UI can be honest up front."""
    from src.tools import tool_registry
    rates = tool_registry.get('hotel_rates')

    # Atlas needs an interactive login, so on a fresh deploy it is often
    # installed but not authenticated. Claiming it is configured would be the
    # kind of confident-but-wrong answer this app exists to avoid.
    atlas_ok, atlas_note = _atlas_status()

    return jsonify({
        'sources': [
            {'id': 'atlas_cli', 'label': 'Atlas CLI',
             'provides': 'real bookable flights',
             'configured': atlas_ok,
             'note': atlas_note},
            {'id': 'booking_rapidapi', 'label': 'Booking.com (RapidAPI)',
             'provides': 'hotel rates, review scores, photographs',
             'configured': bool(getattr(rates, 'configured', False))},
            {'id': 'osm', 'label': 'OpenStreetMap',
             'provides': 'real hotels, coordinates, official websites',
             'configured': True},
            {'id': 'wikimedia', 'label': 'Wikimedia / Wikipedia',
             'provides': 'area descriptions and geotagged photographs',
             'configured': True},
            {'id': 'screenshot', 'label': 'Live screenshots',
             'provides': 'screenshots of hotel websites and map views',
             'configured': _playwright_available()},
            {'id': 'aviationstack', 'label': 'AviationStack',
             'provides': 'live flight delays',
             'configured': bool(os.getenv('AVIATIONSTACK_API_KEY'))},
            {'id': 'ip-api', 'label': 'ip-api.com',
             'provides': 'the traveller\'s location, currency and timezone',
             'configured': True},
            {'id': 'openai', 'label': 'OpenAI',
             'provides': 'the planning agent itself',
             'configured': bool(os.getenv('OPENAI_API_KEY'))},
        ],
        'policy': 'No source is simulated. An unconfigured source yields no data, never invented data.',
    })


# ── agent helpers ─────────────────────────────────────────────────

_agent_singleton = None


def _agent():
    global _agent_singleton
    if _agent_singleton is None:
        from src.agent.trip_agent import TripAgent
        _agent_singleton = TripAgent()
    return _agent_singleton


def _atlas_status():
    """Whether the Atlas CLI is installed and logged in.

    Cached briefly: this runs on every page load and shells out.
    """
    import shutil
    import subprocess
    import time as _time

    cached = getattr(_atlas_status, '_cache', None)
    if cached and _time.time() - cached[0] < 60:
        return cached[1], cached[2]

    ok, note = False, ''
    if not shutil.which('atlas-flight'):
        note = 'atlas-flight is not installed on this host'
    else:
        try:
            proc = subprocess.run(['atlas-flight', 'auth', 'status', '--json'],
                                  capture_output=True, text=True, timeout=15)
            payload = json.loads(proc.stdout or '{}')
            ok = bool((payload.get('data') or {}).get('authenticated'))
            note = '' if ok else 'installed but not logged in — run: atlas-flight auth login'
        except Exception as exc:
            note = f'could not check Atlas auth: {type(exc).__name__}'

    _atlas_status._cache = (_time.time(), ok, note)
    return ok, note


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _brief_from_params(data: dict) -> str:
    """Turn the structured search form into the brief the agent reads."""
    if data.get('request'):
        return data['request']

    bits = []
    origin, dest = data.get('origin', ''), data.get('destination', '')
    if origin and dest:
        bits.append(f'Plan a trip from {origin} to {dest}')
    elif dest:
        bits.append(f'Plan a trip to {dest}')
    else:
        bits.append('Plan a trip')

    depart, ret = data.get('depart_date', ''), data.get('return_date', '')
    if depart and ret:
        bits.append(f'departing {depart} and returning {ret}')
    elif depart:
        bits.append(f'departing {depart}')

    adults = int(data.get('adults', 2) or 2)
    children = int(data.get('children', 0) or 0)
    party = f'{adults} adult' + ('s' if adults != 1 else '')
    if children:
        party += f' and {children} child' + ('ren' if children != 1 else '')
    bits.append(f'for {party}')

    budget = float(data.get('budget', 0) or 0)
    if budget:
        bits.append(f"with a total budget of {budget:.0f} {data.get('currency', 'USD')}")

    prefs = data.get('preferences') or {}
    wants = [k.replace('_', ' ') for k, v in prefs.items() if v is True]
    if prefs.get('stars_min'):
        wants.append(f"at least {prefs['stars_min']} stars")
    if prefs.get('hotel_area'):
        wants.append(f"staying in {prefs['hotel_area']}")
    if wants:
        bits.append('Preferences: ' + ', '.join(wants))

    bits.append('Show a real image for each hotel you recommend.')
    return '. '.join(bits) + '.'


def _trip_from(result: dict) -> dict:
    """Assemble the one costed trip the UI leads with.

    Pairing the cheapest flight with the best-value stay is a presentation
    decision, so it lives here rather than being asked of the model — and the
    total is only shown when both halves actually have a price.
    """
    artifacts = result.get('artifacts') or {}
    flights = artifacts.get('flights') or []
    hotels = artifacts.get('hotels') or []
    locale = artifacts.get('locale') or {}

    flight = min(flights, key=lambda f: f.get('price_total') or 1e9) if flights else None

    # A flexible-date search returns whole offers too. Without this, asking
    # "whenever is cheapest" produced windows but no flight to look at.
    windows = artifacts.get('windows') or []
    if flight is None and windows:
        best_window = min(windows, key=lambda w: w.get('price_total') or 1e9)
        flight = best_window.get('offer')
    priced = [h for h in hotels if h.get('total_price') is not None]
    hotel = min(priced, key=lambda h: h['total_price']) if priced else (hotels[0] if hotels else None)

    flight_price = (flight or {}).get('price_total')
    hotel_price = (hotel or {}).get('total_price')
    total = None
    if flight_price is not None and hotel_price is not None:
        total = round(flight_price + hotel_price, 2)
    elif hotel_price is not None:
        total = hotel_price
    elif flight_price is not None:
        total = flight_price

    # Currencies can differ between providers; never add across them.
    currencies = {c for c in ((flight or {}).get('currency'), (hotel or {}).get('currency')) if c}
    mixed = len(currencies) > 1
    if mixed:
        total = None

    return {
        'flight': flight,
        'hotel': hotel,
        'flight_price': flight_price,
        'hotel_price': hotel_price,
        'total': total,
        'currency': (flight or {}).get('currency') or (hotel or {}).get('currency')
                    or locale.get('currency') or 'USD',
        'mixed_currency': mixed,
        'currencies': sorted(currencies),
        'passengers': (flight or {}).get('passengers'),
        'nights': (hotel or {}).get('nights'),
        'windows': windows,
        'airports': artifacts.get('airports') or [],
        'locale': locale or None,
        'alternatives': [h for h in hotels if h is not hotel][:8],
    }


def _snapshot(session) -> dict:
    """What we knew before this turn, for comparing against afterwards."""
    if session is None:
        return {}
    artifacts = session.artifacts or {}
    return {
        'hotels': {h.get('hotel_id'): h.get('total_price')
                   for h in (artifacts.get('hotels') or []) if h.get('hotel_id')},
        'flight_price': _best_flight(artifacts).get('price_total'),
        'dates': (_best_flight(artifacts).get('outbound') or {}).get('depart', '')[:10],
    }


def _best_flight(artifacts: dict) -> dict:
    """The cheapest flight we hold, wherever it came from.

    A flexible-date search stores offers under `windows`, not `flights`, so
    looking only at `flights` made every price comparison come back empty.
    """
    flights = artifacts.get('flights') or []
    if flights:
        return min(flights, key=lambda f: f.get('price_total') or 1e9) or {}
    windows = artifacts.get('windows') or []
    if windows:
        return (min(windows, key=lambda w: w.get('price_total') or 1e9) or {}).get('offer') or {}
    return {}


def _cards_from(result: dict, before: dict) -> list:
    """Structured cards for a reply, so an answer is not only prose.

    A traveller asking "what if we left on the 26th?" wants to see the number
    move, not read a paragraph about it. These carry the parts worth showing:
    what a price did, and which stay is being talked about.
    """
    cards = []
    artifacts = result.get('artifacts') or {}
    hotels = artifacts.get('hotels') or []
    answer = (result.get('answer') or '').lower()

    # What the flight fare did between turns.
    now_flight = _best_flight(artifacts)

    was = before.get('flight_price')
    now = (now_flight or {}).get('price_total')
    if was is not None and now is not None and abs(now - was) > 0.01:
        cards.append({
            'kind': 'price_change',
            'title': 'Flights',
            'from': round(was, 2), 'to': round(now, 2),
            'delta': round(now - was, 2),
            'currency': (now_flight or {}).get('currency', 'USD'),
            'detail': (f"{now_flight.get('airline_name') or ''} "
                       f"{now_flight.get('flight_code')} "
                       f"{now_flight.get('origin')}→{now_flight.get('destination')}".strip()
                       if now_flight else ''),
        })

    # Stays whose price moved since the last turn.
    for hotel in hotels:
        hid, price = hotel.get('hotel_id'), hotel.get('total_price')
        prev = before.get('hotels', {}).get(hid)
        if prev is not None and price is not None and abs(price - prev) > 0.01:
            cards.append({
                'kind': 'price_change',
                'title': hotel.get('name', 'Stay'),
                'from': round(prev, 2), 'to': round(price, 2),
                'delta': round(price - prev, 2),
                'currency': hotel.get('currency', 'USD'),
                'detail': f"{hotel.get('nights')} nights" if hotel.get('nights') else '',
            })

    # The flight itself, when the reply is about flying rather than staying.
    if now_flight:
        code = (now_flight.get('flight_code') or '').lower()
        airline = (now_flight.get('airline_name') or '').lower()
        mentions_flight = (
            (code and code in answer) or (airline and airline in answer)
            or any(word in answer for word in ('flight', 'fly', 'flying', 'departs', 'airline'))
        )
        already_priced = any(c['kind'] == 'price_change' and c['title'] == 'Flights'
                             for c in cards)
        if mentions_flight and not already_priced:
            cards.append({
                'kind': 'flight',
                'airline_name': now_flight.get('airline_name'),
                'flight_code': now_flight.get('flight_code'),
                'origin': now_flight.get('origin'),
                'destination': now_flight.get('destination'),
                'outbound': now_flight.get('outbound'),
                'return_leg': now_flight.get('return_leg'),
                'price_total': now_flight.get('price_total'),
                'price_per_passenger': now_flight.get('price_per_passenger'),
                'passengers': now_flight.get('passengers'),
                'currency': now_flight.get('currency'),
                'offer_id': now_flight.get('offer_id'),
            })

    # Whichever stays the reply is actually about, so the answer has a face.
    named = [h for h in hotels if h.get('name') and h['name'].lower() in answer]
    for hotel in named[:2]:
        cards.append({
            'kind': 'stay',
            'hotel_id': hotel.get('hotel_id'),
            'name': hotel.get('name'),
            'area': hotel.get('area'),
            'image_url': hotel.get('image_url'),
            'review_score': hotel.get('review_score'),
            'review_count': hotel.get('review_count'),
            'total_price': hotel.get('total_price'),
            'price_per_night': hotel.get('price_per_night'),
            'currency': hotel.get('currency'),
            'nights': hotel.get('nights'),
            'booking_url': hotel.get('booking_url') or hotel.get('website'),
        })

    return cards[:4]


def _follow_ups(result: dict) -> list:
    """Two or three questions worth asking next.

    Written by a small model against the answer that was actually given, so
    they follow the conversation rather than being a fixed menu. Falls back to
    questions derived from the results if that call fails — a follow-up strip
    is never worth failing a request over.
    """
    artifacts = result.get('artifacts') or {}
    hotels = artifacts.get('hotels') or []
    named = hotels[0].get('name') if hotels else None

    fallback = [q for q in (
        f'Is {named} quiet at night?' if named else None,
        f'What is within walking distance of {named}?' if named else None,
        'Which dates would save the most?' if artifacts.get('windows') else None,
        'Anything with a pool?',
    ) if q][:3]

    if not os.getenv('OPENAI_API_KEY'):
        return fallback

    try:
        import openai
        client = openai.OpenAI()
        reply = client.chat.completions.create(
            model='gpt-4o-mini', temperature=0.4, max_tokens=120,
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content':
                 'You suggest what a traveller might ask next. Return JSON '
                 '{"questions": ["...", "...", "..."]}. Each is one short '
                 'question in the traveller\'s voice, under 9 words, answerable '
                 'from flights, hotel rates, photos, maps or area information. '
                 'Name real hotels or dates from the context. Never repeat what '
                 'the answer already said.'},
                {'role': 'user', 'content':
                 f"They asked: {result.get('request', '')}\n\n"
                 f"Answer given: {(result.get('answer') or '')[:900]}\n\n"
                 f"Stays available: {', '.join(h.get('name', '') for h in hotels[:5])}"},
            ],
        )
        questions = json.loads(reply.choices[0].message.content).get('questions') or []
        cleaned = [q.strip() for q in questions if isinstance(q, str) and 3 < len(q.strip()) < 90]
        return cleaned[:3] or fallback
    except Exception as exc:
        logger.debug('follow-up generation failed: %s', exc)
        return fallback


def _combos_from(result: dict) -> list:
    """A few air + hotel combinations, each with a total and a reason.

    The results page used to show one trip plus a wall of supporting detail.
    A traveller is choosing between whole trips, so the page leads with two or
    three costed combinations and everything else waits to be asked for.

    Only pairings we can actually price appear here; a hotel with no rate is
    not quietly turned into a total.
    """
    artifacts = result.get('artifacts') or {}
    flights = artifacts.get('flights') or []
    hotels = [h for h in (artifacts.get('hotels') or []) if h.get('total_price') is not None]
    if not hotels:
        return []

    flight = min(flights, key=lambda f: f.get('price_total') or 1e9) if flights else None

    # A flexible-date search returns whole offers but never populates
    # artifacts['flights'], so asking for the cheapest window produced combos
    # labelled "stay only" even though a flight had been priced.
    if flight is None:
        windows = artifacts.get('windows') or []
        if windows:
            flight = min(windows, key=lambda w: w.get('price_total') or 1e9).get('offer')

    flight_price = (flight or {}).get('price_total')
    flight_currency = (flight or {}).get('currency')

    # Never add across currencies — we hold no exchange rates.
    if flight and flight_currency and hotels[0].get('currency') \
            and flight_currency != hotels[0]['currency']:
        flight, flight_price = None, None

    cheapest = min(hotels, key=lambda h: h['total_price'])
    rated = [h for h in hotels if (h.get('review_score') or 0) > 0]
    best_rated = max(rated, key=lambda h: h['review_score']) if rated else None

    # Best value: the highest review score per unit of money, so it is a real
    # trade-off rather than a third way of saying "cheapest".
    def value(h):
        score = h.get('review_score') or 0
        return score / h['total_price'] if h['total_price'] else 0
    best_value = max(rated, key=value) if rated else None

    picks = []
    for hotel, label, why in (
        (best_value, 'Best value', 'the best reviews for the money'),
        (cheapest, 'Cheapest', 'the lowest total we found'),
        (best_rated, 'Best reviewed', 'the highest-rated stay available'),
    ):
        if hotel is None or any(p['hotel']['hotel_id'] == hotel.get('hotel_id') for p in picks):
            continue
        total = (round(flight_price + hotel['total_price'], 2)
                 if flight_price is not None else hotel['total_price'])
        picks.append({
            'label': label,
            'why': why,
            'hotel': hotel,
            'flight': flight,
            'hotel_price': hotel['total_price'],
            'flight_price': flight_price,
            'total': total,
            'includes_flight': flight_price is not None,
            'currency': hotel.get('currency') or flight_currency or 'USD',
            'nights': hotel.get('nights'),
            'passengers': (flight or {}).get('passengers'),
        })

    picks.sort(key=lambda p: p['total'])
    return picks[:3]


def _packages_from(result: dict) -> list:
    """Shape the agent's picks for the existing card UI.

    Only hotels the agent actually surfaced appear here, each carrying its
    provenance so the card can show where the data came from.
    """
    hotels = (result.get('artifacts') or {}).get('hotels') or []
    flights = (result.get('artifacts') or {}).get('flights') or []
    cheapest_flight = min(flights, key=lambda f: f.get('price') or 1e9) if flights else None

    packages = []
    for hotel in hotels[:6]:
        hotel_price = hotel.get('total_price')
        flight_price = (cheapest_flight or {}).get('price') if cheapest_flight else None
        total = None
        if hotel_price is not None and flight_price is not None:
            total = round(hotel_price + flight_price, 2)
        elif hotel_price is not None:
            total = hotel_price

        packages.append({
            'label': hotel.get('name', ''),
            'hotel': hotel,
            'flights': [cheapest_flight] if cheapest_flight else [],
            'hotel_price': hotel_price,
            'flight_price': flight_price,
            'total_price': total,
            'currency': hotel.get('currency') or 'USD',
            'price_available': hotel_price is not None,
            'image_url': hotel.get('image_url'),
            'image_source': hotel.get('image_source'),
            'provenance': hotel.get('provenance'),
        })
    return packages


# ── Session Context & Voice Endpoints ─────────────────────────────

@app.route('/api/context')
def get_context():
    """Return current session context for the chat sidebar"""
    return jsonify({
        'state': checkpoint_manager.state.value,
        'destination': checkpoint_manager.itinerary.destination if checkpoint_manager.itinerary else None,
        'options_count': len(current_options),
        'has_checkpoint': checkpoint_manager.current_checkpoint is not None,
        'checkpoint': checkpoint_manager.current_checkpoint.to_dict() if checkpoint_manager.current_checkpoint else None,
    })


@app.route('/api/voice-command', methods=['POST'])
def voice_command():
    """Parse voice transcript into structured action using LLM"""
    try:
        data = request.json
        transcript = data.get('transcript', '')
        page_context = data.get('context', {})  # current page, filters, etc.
        
        # Use reasoning engine (OpenAI) to parse intent
        # System prompt instructs LLM to return structured JSON
        system_prompt = '''You are a travel assistant voice command parser. Parse the user's voice command into a structured action.
Return JSON with:
- action: one of "filter", "search", "navigate", "book", "info", "compare"
- filters: object with any of: stars_min, stars_max, max_price, min_price, amenities (array), area, hotel_name, airline, departure_time
- search_params: object with origin, destination, depart_date, return_date, adults, budget (if action is "search")
- navigate_to: page path (if action is "navigate") - one of "/", "/explore", "/results", "/booking", "/trips"
- response_text: short confirmation text to display/speak to the user
- speak: boolean, whether to speak the response
Only return valid JSON, no explanation.'''
        
        import openai
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context: User is on {page_context.get('page', 'home')} page. Current filters: {page_context.get('filters', {})}. Command: {transcript}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        
        result = json.loads(response.choices[0].message.content)
        return jsonify({'success': True, **result})
    
    except Exception as e:
        # Fallback: treat as chat message
        return jsonify({
            'success': True,
            'action': 'chat',
            'response_text': f"I heard: {transcript}. Let me help with that.",
            'speak': False,
            'fallback': True,
        })


@app.route('/api/tts', methods=['POST'])
def text_to_speech():
    """Proxy text to ElevenLabs TTS, return audio stream"""
    try:
        elevenlabs_key = os.getenv('ELEVENLABS_API_KEY', '')
        if not elevenlabs_key:
            return jsonify({'error': 'TTS not configured', 'silent': True}), 503
        
        data = request.json
        text = data.get('text', '')
        voice_id = data.get('voice_id', 'EXAVITQu4vr4xnSDxMaL')  # Default: "Sarah" voice
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Call ElevenLabs API
        import requests as req
        tts_response = req.post(
            f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}',
            headers={
                'xi-api-key': elevenlabs_key,
                'Content-Type': 'application/json',
            },
            json={
                'text': text,
                'model_id': 'eleven_flash_v2_5',
                'voice_settings': {
                    'stability': 0.5,
                    'similarity_boost': 0.75,
                }
            },
            timeout=10,
        )
        
        if tts_response.status_code != 200:
            return jsonify({'error': 'TTS generation failed', 'silent': True}), 503
        
        # Track the API call
        tracker.record_elevenlabs(
            endpoint='text-to-speech',
            characters=len(text),
            status='success',
        )
        
        return Response(
            tts_response.content,
            mimetype='audio/mpeg',
            headers={'Content-Disposition': 'inline'}
        )
    
    except Exception as e:
        return jsonify({'error': str(e), 'silent': True}), 503


@app.route('/api/voice/transcribe', methods=['POST'])
def voice_transcribe():
    """Transcribe recorded audio with ElevenLabs Scribe.

    Takes a multipart upload under `audio` (whatever MediaRecorder produced)
    and returns the text. Used for voice input so transcription quality does
    not depend on which browser the traveller is using.
    """
    key = os.getenv('ELEVENLABS_API_KEY', '')
    if not key:
        return jsonify({'success': False,
                        'error': 'ELEVENLABS_API_KEY is not set, so voice input is unavailable'}), 503

    clip = request.files.get('audio')
    if clip is None:
        return jsonify({'success': False, 'error': 'no audio uploaded'}), 400

    import time as _time
    import requests as req
    started = _time.time()
    try:
        resp = req.post(
            'https://api.elevenlabs.io/v1/speech-to-text',
            headers={'xi-api-key': key},
            files={'file': (clip.filename or 'clip.webm', clip.stream,
                            clip.mimetype or 'audio/webm')},
            data={'model_id': 'scribe_v1'},
            timeout=60,
        )
    except Exception as e:
        app.logger.exception('transcription failed')
        return jsonify({'success': False, 'error': f'transcription request failed: {e}'}), 503

    duration_ms = int((_time.time() - started) * 1000)
    if resp.status_code != 200:
        return jsonify({'success': False,
                        'error': f'ElevenLabs returned {resp.status_code}',
                        'detail': resp.text[:300]}), 502

    body = resp.json()
    try:
        tracker.record_elevenlabs(endpoint='speech-to-text',
                                  characters=len(body.get('text', '')),
                                  status='success')
    except Exception:
        pass

    return jsonify({
        'success': True,
        'text': body.get('text', ''),
        'language': body.get('language_code', ''),
        'confidence': body.get('language_probability'),
        'duration_ms': duration_ms,
    })


@app.route('/api/voice/speak', methods=['POST'])
def voice_speak():
    """Stream spoken audio for a reply.

    Uses the streaming endpoint and the turbo model: a short sentence comes
    back in roughly 300ms, which is quick enough to answer out loud.
    """
    key = os.getenv('ELEVENLABS_API_KEY', '')
    if not key:
        return jsonify({'error': 'voice output not configured', 'silent': True}), 503

    data = request.json or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'no text provided'}), 400

    # Long answers are expensive and nobody listens to a four-minute reply.
    text = text[:1200]
    voice_id = data.get('voice_id', DEFAULT_VOICE_ID)

    import requests as req
    try:
        upstream = req.post(
            f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream',
            headers={'xi-api-key': key, 'Content-Type': 'application/json'},
            json={'text': text,
                  'model_id': data.get('model_id', 'eleven_turbo_v2_5'),
                  'output_format': 'mp3_44100_128',
                  'voice_settings': {'stability': 0.45, 'similarity_boost': 0.75,
                                     'speed': float(data.get('speed', 1.0))}},
            timeout=45, stream=True,
        )
    except Exception as e:
        app.logger.exception('tts failed')
        return jsonify({'error': str(e), 'silent': True}), 503

    if upstream.status_code != 200:
        return jsonify({'error': f'ElevenLabs returned {upstream.status_code}',
                        'detail': upstream.text[:300], 'silent': True}), 502

    try:
        tracker.record_elevenlabs(endpoint='text-to-speech-stream',
                                  characters=len(text), status='success')
    except Exception:
        pass

    return Response(upstream.iter_content(chunk_size=4096), mimetype='audio/mpeg',
                    headers={'Cache-Control': 'no-cache',
                             'Content-Disposition': 'inline'})


@app.route('/api/voice/status')
def voice_status():
    """Whether voice in and voice out are usable right now."""
    configured = bool(os.getenv('ELEVENLABS_API_KEY'))
    return jsonify({
        'input': {'available': configured, 'provider': 'ElevenLabs Scribe',
                  'note': '' if configured else 'set ELEVENLABS_API_KEY to enable'},
        'output': {'available': configured, 'provider': 'ElevenLabs Turbo v2.5',
                   'note': '' if configured else 'set ELEVENLABS_API_KEY to enable'},
        'voices': VOICE_CHOICES,
    })


@app.route('/agent')
def agent_console():
    """Console showing what the agent called, what it found, and from where."""
    return render_template('agent.html')


# ── Vite React app (voice-enabled agent UI) ─────────────────────────

_AGENT_APP_DIR = os.path.join(os.path.dirname(__file__), 'agent-app')


@app.route('/app')
@app.route('/app/')
def agent_app_index():
    """The React UI. Built from web/ with `npm run build`."""
    from flask import send_from_directory
    index = os.path.join(_AGENT_APP_DIR, 'index.html')
    if not os.path.exists(index):
        return ('<h1>UI not built</h1>'
                '<p>Run <code>cd web &amp;&amp; npm install &amp;&amp; npm run build</code>.</p>'), 501
    return send_from_directory(_AGENT_APP_DIR, 'index.html')


@app.route('/app/<path:path>')
def agent_app_asset(path):
    from flask import send_from_directory
    full = os.path.join(_AGENT_APP_DIR, path)
    if os.path.exists(full) and os.path.isfile(full):
        return send_from_directory(_AGENT_APP_DIR, path)
    return send_from_directory(_AGENT_APP_DIR, 'index.html')


# ── SPA Catch-All (must be LAST route) ──────────────────────────────

import os as _os

_SPA_DIR = _os.path.join(_os.path.dirname(__file__), 'spa-build')

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_spa(path):
    """Serve the React SPA for all non-API routes"""
    from flask import send_from_directory
    # If a specific file exists (JS, CSS, assets), serve it
    if path and _os.path.exists(_os.path.join(_SPA_DIR, path)):
        return send_from_directory(_SPA_DIR, path)
    # Otherwise serve index.html (React Router handles routing)
    if _os.path.exists(_os.path.join(_SPA_DIR, 'index.html')):
        return send_from_directory(_SPA_DIR, 'index.html')
    # Fallback to template if SPA not built
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=2000)
