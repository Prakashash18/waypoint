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
from src.agent import (
    SearchEngine, DisruptedItinerary, RankedOption,
    CheckpointManager, Checkpoint, CheckpointType, CheckpointDecision,
    AuditTrail, AuditEvent, AuditEventType,
    ReasoningEngine,
    LocationService, FlightStatusService,
    tracker
)


app = Flask(__name__)
CORS(app)

# Global state (for demo purposes - in production, use proper session management)
cli = AtlasCLI()
audit = AuditTrail()
reasoning = ReasoningEngine()
checkpoint_manager = CheckpointManager(cli, audit, reasoning)
current_options = []


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
        
        # Find nearby airports
        nearby = LocationService.find_nearby_airports(lat, lon, radius_km=200)
        
        return jsonify({
            'success': True,
            'airports': nearby,
            'location': {'lat': lat, 'lon': lon}
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400


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


@app.route('/api/tracker/simulate', methods=['POST'])
def toggle_simulate():
    """Toggle simulated delay data"""
    data = request.get_json()
    enabled = data.get('enabled', True)
    tracker.simulate_delays = enabled
    
    return jsonify({
        'success': True,
        'simulate_delays': enabled,
        'message': f"Simulated delays {'enabled' if enabled else 'disabled'}. "
                   f"{'Showing fake data from Changi' if enabled else 'Showing real data from AviationStack'}"
    })


# ── Plan My Trip (Tool Registry) ──────────────────────────────────

@app.route('/api/tools', methods=['GET'])
def list_tools():
    """List all registered tools and their capabilities"""
    from src.tools import tool_registry
    return jsonify(tool_registry.to_dict())


@app.route('/api/plan-trip', methods=['POST'])
def plan_trip():
    """Plan a trip using the TripComposer — searches flights + hotels in parallel."""
    try:
        from src.tools.composer import TripComposer, TripRequest
        from src.tools import tool_registry
        
        data = request.json
        
        trip_request = TripRequest(
            origin=data.get('origin', ''),
            destination=data.get('destination', ''),
            depart_date=data.get('depart_date', ''),
            return_date=data.get('return_date', ''),
            adults=data.get('adults', 2),
            children=data.get('children', 0),
            budget=float(data.get('budget', 0)),
            currency=data.get('currency', 'USD'),
            preferences=data.get('preferences', {}),
        )
        
        composer = TripComposer(tool_registry)
        result = composer.plan(trip_request)
        
        # Add helpful message when no packages were found
        packages = result.get('packages', [])
        if not packages:
            summary = result.get('summary', '')
            origin = trip_request.origin
            destination = trip_request.destination
            depart = trip_request.depart_date
            result['message'] = (
                f"No flights or hotels found for {origin} to {destination} "
                f"on {depart}. Try different dates, a different route, or check "
                f"that the city names are spelled correctly. "
                f"{summary}"
            ).strip()
        
        return jsonify({
            'success': True,
            **result,
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'response': f"I ran into a problem planning your trip: {str(e)}",
            'error': str(e)
        }), 400


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
