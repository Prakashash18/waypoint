"""
Reasoning Engine
Uses OpenAI GPT-4 for tradeoff generation, explanations, and conversation
"""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime

# Try to import openai, fall back to mock if not available
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .search import RankedOption, DisruptedItinerary
from .api_tracker import tracker


class ReasoningEngine:
    """Generates human-readable tradeoffs and explanations using OpenAI GPT-4"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        
        if OPENAI_AVAILABLE and self.api_key:
            self.client = OpenAI(api_key=self.api_key)
        else:
            self.client = None
    
    def generate_tradeoffs(
        self,
        options: List[RankedOption],
        itinerary: DisruptedItinerary
    ) -> List[str]:
        """Generate tradeoff descriptions for each option"""
        tradeoffs = []
        
        for option in options:
            if self.client:
                tradeoff = self._generate_tradeoff_with_openai(option, itinerary)
            else:
                tradeoff = self._generate_tradeoff_mock(option, itinerary)
            
            tradeoffs.append(tradeoff)
            option.tradeoff = tradeoff
        
        return tradeoffs
    
    def _generate_tradeoff_with_openai(
        self,
        option: RankedOption,
        itinerary: DisruptedItinerary
    ) -> str:
        """Generate tradeoff using OpenAI GPT-4"""
        prompt = f"""You are a travel assistant helping a stranded passenger.

Original flight: {itinerary.origin} to {itinerary.destination}
Original departure: {itinerary.original_departure.strftime('%Y-%m-%d %H:%M')}
{"Hard deadline: Must arrive before " + itinerary.hard_deadline.strftime('%Y-%m-%d %H:%M') if itinerary.hard_deadline else "No hard deadline"}

Replacement option:
- Flight: {option.airline} {option.flight_number}
- Departure: {option.departure.strftime('%Y-%m-%d %H:%M')}
- Arrival: {option.arrival.strftime('%Y-%m-%d %H:%M')}
- Price: ${option.price} {option.currency}
- Fare: {option.fare_family}
- Baggage included: {"Yes" if option.baggage_included else "No"}
- Meets deadline: {"Yes" if option.meets_deadline else "No"}

Write ONE concise sentence (max 20 words) explaining the key tradeoff of this option.
Focus on what makes this option notable compared to others.
Examples: "Cheapest but arrives 4h after your deadline" or "Only option that makes the meeting, +$180"

Tradeoff:"""

        try:
            import time
            start = time.time()
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0.7
            )
            duration_ms = int((time.time() - start) * 1000)
            usage = response.usage
            tracker.record_openai(
                model="gpt-4",
                tokens_in=usage.prompt_tokens if usage else 0,
                tokens_out=usage.completion_tokens if usage else 0,
                endpoint="chat.completions",
                duration_ms=duration_ms,
            )
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            tracker.record_openai(
                model="gpt-4",
                tokens_in=0, tokens_out=0,
                endpoint="chat.completions",
                status="error",
            )
            # Fall back to mock
            return self._generate_tradeoff_mock(option, itinerary)
    
    def _generate_tradeoff_mock(
        self,
        option: RankedOption,
        itinerary: DisruptedItinerary
    ) -> str:
        """Generate tradeoff using simple rules (mock mode)"""
        parts = []
        
        # Check deadline
        if itinerary.hard_deadline:
            if not option.meets_deadline:
                delay_minutes = int((option.arrival - itinerary.hard_deadline).total_seconds() / 60)
                parts.append(f"arrives {delay_minutes}min after your deadline")
            else:
                parts.append("meets your deadline")
        
        # Check price relative to rank
        if option.rank == 1:
            parts.append("best overall value")
        elif option.price < 200:
            parts.append("budget-friendly option")
        elif option.price > 350:
            parts.append("premium pricing")
        
        # Check baggage
        if option.baggage_included:
            parts.append("includes baggage")
        
        # Check availability
        if option.seats_available <= 2:
            parts.append("limited seats remaining")
        
        if not parts:
            parts.append(f"departs {option.departure.strftime('%H:%M')}")
        
        return ", ".join(parts).capitalize()
    
    def explain_checkpoint(
        self,
        checkpoint_type: str,
        context: Dict[str, Any]
    ) -> str:
        """Generate explanation for a checkpoint decision"""
        if self.client:
            return self._explain_with_openai(checkpoint_type, context)
        else:
            return self._explain_mock(checkpoint_type, context)
    
    def _explain_with_openai(
        self,
        checkpoint_type: str,
        context: Dict[str, Any]
    ) -> str:
        """Generate explanation using OpenAI GPT-4"""
        import json
        prompt = f"""You are a travel agent explaining a decision to a passenger.

Checkpoint type: {checkpoint_type}
Context: {json.dumps(context, indent=2, default=str)}

Write a brief, clear explanation (2-3 sentences) of what you're asking permission for and why.
Be transparent about any changes or tradeoffs.

Explanation:"""

        try:
            import time
            start = time.time()
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.7
            )
            duration_ms = int((time.time() - start) * 1000)
            usage = response.usage
            tracker.record_openai(
                model="gpt-4",
                tokens_in=usage.prompt_tokens if usage else 0,
                tokens_out=usage.completion_tokens if usage else 0,
                endpoint="explain_checkpoint",
                duration_ms=duration_ms,
            )
            return response.choices[0].message.content.strip()
        
        except Exception:
            tracker.record_openai(
                model="gpt-4", tokens_in=0, tokens_out=0,
                endpoint="explain_checkpoint", status="error",
            )
            return self._explain_mock(checkpoint_type, context)
    
    def _explain_mock(
        self,
        checkpoint_type: str,
        context: Dict[str, Any]
    ) -> str:
        """Generate explanation using templates (mock mode)"""
        if checkpoint_type == 'INITIAL_BOOKING':
            option = context.get('selected_option', {})
            return f"I found a replacement flight {option.get('flight_number')} departing at {option.get('departure')}. This option {option.get('tradeoff', 'meets your requirements')}. Shall I proceed with booking?"
        
        elif checkpoint_type == 'PRICE_CHANGE':
            original = context.get('original_price', 0)
            new = context.get('new_price', 0)
            diff = new - original
            return f"The price has increased by ${diff:.2f} since we started. The new total is ${new:.2f}. This is common with dynamic pricing. Would you like to proceed at the new price?"
        
        elif checkpoint_type == 'SEAT_FALLBACK':
            return f"Your preferred seat is not available. I've selected an alternative seat. Would you like to proceed with this seat assignment?"
        
        elif checkpoint_type == 'FINAL_PAYMENT':
            total = context.get('total_amount', 0)
            return f"Ready to process payment of ${total:.2f} from your Atlas balance. This will issue your ticket. Confirm to proceed."
        
        return "Please review the details and confirm to proceed."
    
    def parse_cancellation_email(self, email_text: str) -> Dict[str, Any]:
        """Parse a cancellation email to extract itinerary details"""
        if self.client:
            return self._parse_email_with_openai(email_text)
        else:
            return self._parse_email_mock(email_text)
    
    def _parse_email_with_openai(self, email_text: str) -> Dict[str, Any]:
        """Parse email using OpenAI GPT-4"""
        prompt = f"""Extract flight details from this cancellation email or message.

Message:
{email_text}

Extract and return as JSON with these exact keys:
- origin (3-letter IATA airport code, e.g. "KUL")
- destination (3-letter IATA airport code, e.g. "SIN")
- original_departure (ISO 8601 datetime, e.g. "2026-09-15T08:00:00Z")
- passengers (number, default 1)
- hard_deadline (ISO 8601 datetime or null if not mentioned)
- pnr (booking reference if mentioned, otherwise null)

If information is not available, use reasonable defaults or null.
Return ONLY the JSON, no other text.

JSON:"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.3
            )
            
            import json
            content = response.choices[0].message.content.strip()
            # Remove markdown code blocks if present
            if content.startswith('```'):
                content = content.split('\n')[1:-1][0] if '\n' in content else content[3:-3]
            return json.loads(content)
        
        except Exception:
            return self._parse_email_mock(email_text)
    
    def _parse_email_mock(self, email_text: str) -> Dict[str, Any]:
        """Parse email using simple extraction (mock mode)"""
        # For demo purposes, return hardcoded data
        return {
            'origin': 'KUL',
            'destination': 'SIN',
            'original_departure': '2026-09-15T08:00:00Z',
            'passengers': 1,
            'hard_deadline': '2026-09-15T13:00:00Z',
            'pnr': 'ABC123',
            'notes': 'Extracted from cancellation email'
        }
    
    def chat(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Handle conversational interaction with the agent"""
        if self.client:
            return self._chat_with_openai(user_message, context)
        else:
            return self._chat_mock(user_message, context)
    
    def _chat_with_openai(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Chat using OpenAI GPT-4"""
        system_prompt = """You are Waypoint, an empathetic travel assistant helping a stranded passenger whose flight was cancelled.

Your role:
1. Listen to their concerns and frustrations
2. Extract flight details from their messages (origin, destination, departure time, passengers, deadlines)
3. Explain what you're doing and why
4. Guide them through the rebooking process
5. Be empathetic but professional

You can help with:
- Understanding their situation
- Explaining flight options and tradeoffs
- Answering questions about the booking process
- Providing updates on status

Always be understanding about their frustration. Acknowledge their feelings before moving to solutions.

If they mention specific details about their cancelled flight, extract them and confirm what you understood."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        if context:
            messages.insert(1, {"role": "system", "content": f"Current context: {context}"})
        
        try:
            import time
            start = time.time()
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            duration_ms = int((time.time() - start) * 1000)
            usage = response.usage
            tracker.record_openai(
                model="gpt-4",
                tokens_in=usage.prompt_tokens if usage else 0,
                tokens_out=usage.completion_tokens if usage else 0,
                endpoint="chat",
                duration_ms=duration_ms,
            )
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            tracker.record_openai(
                model="gpt-4", tokens_in=0, tokens_out=0,
                endpoint="chat", status="error",
            )
            return f"I'm having trouble connecting right now. Could you please try again? Error: {str(e)}"
    
    def _chat_mock(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Mock chat response"""
        return "I understand your frustration with the flight cancellation. Let me help you find a replacement flight. Could you tell me your origin and destination airports, and when you need to arrive by?"
    
    def analyze_image(self, image_base64: str, user_query: str = "") -> Dict[str, Any]:
        """Analyze an image (e.g., boarding pass, cancellation notice)"""
        if self.client:
            return self._analyze_image_with_openai(image_base64, user_query)
        else:
            return self._parse_email_mock("Extracted from image")
    
    def _analyze_image_with_openai(self, image_base64: str, user_query: str) -> Dict[str, Any]:
        """Analyze image using GPT-4 Vision"""
        prompt = f"""Analyze this image related to a flight cancellation or booking.

{user_query if user_query else "Extract any relevant flight information like PNR, flight number, airports, dates, times."}

Return as JSON with these keys if available:
- pnr (booking reference)
- flight_number
- origin (3-letter IATA code)
- destination (3-letter IATA code)
- departure (ISO 8601 datetime)
- passenger_name
- any_other_details

JSON:"""

        try:
            import time
            start = time.time()
            response = self.client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            duration_ms = int((time.time() - start) * 1000)
            usage = response.usage
            tracker.record_openai(
                model="gpt-4-vision-preview",
                tokens_in=usage.prompt_tokens if usage else 0,
                tokens_out=usage.completion_tokens if usage else 0,
                endpoint="analyze_image",
                duration_ms=duration_ms,
            )
            
            import json
            content = response.choices[0].message.content.strip()
            if content.startswith('```'):
                content = content.split('\n')[1:-1][0] if '\n' in content else content[3:-3]
            return json.loads(content)
        
        except Exception:
            tracker.record_openai(
                model="gpt-4-vision-preview", tokens_in=0, tokens_out=0,
                endpoint="analyze_image", status="error",
            )
            return self._parse_email_mock("Extracted from image")
