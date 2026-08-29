#!/usr/bin/env python3
"""
Waypoint Demo Script
Demonstrates end-to-end flow via CLI for testing and screen recording
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.cli import AtlasCLI
from src.agent import (
    SearchEngine, DisruptedItinerary,
    CheckpointManager, CheckpointDecision,
    AuditTrail,
    ReasoningEngine
)


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_checkpoint(checkpoint):
    print(f"\n{'─' * 70}")
    print(f"⚠️  CHECKPOINT: {checkpoint.checkpoint_type.value.replace('_', ' ').upper()}")
    print(f"{'─' * 70}")
    print(f"Title: {checkpoint.title}")
    print(f"Description: {checkpoint.description}")
    print(f"\nReasoning:\n  {checkpoint.reasoning}")
    print(f"\nWhat Changed:\n  {checkpoint.what_changed}")
    print(f"\nCLI Command:\n  $ {checkpoint.cli_command}")
    print(f"{'─' * 70}\n")


def main():
    print_section("🛫 Waypoint — Disruption Rebooking Agent Demo")
    
    # Initialize components
    print("Initializing components...")
    cli = AtlasCLI()
    audit = AuditTrail()
    reasoning = ReasoningEngine()
    checkpoint_manager = CheckpointManager(cli, audit, reasoning)
    
    # Define disrupted itinerary
    print_section("Step 1: Disruption Intake")
    
    # Set departure to tomorrow
    tomorrow = datetime.utcnow() + timedelta(days=1)
    tomorrow = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)
    
    # Set hard deadline (must arrive before 1pm)
    deadline = tomorrow.replace(hour=13, minute=0, second=0, microsecond=0)
    
    itinerary = DisruptedItinerary(
        origin='KUL',
        destination='SIN',
        original_departure=tomorrow,
        passengers=1,
        hard_deadline=deadline,
        notes='Must arrive before 9am meeting'
    )
    
    print(f"Origin: {itinerary.origin}")
    print(f"Destination: {itinerary.destination}")
    print(f"Original Departure: {itinerary.original_departure.strftime('%Y-%m-%d %H:%M')}")
    print(f"Hard Deadline: {itinerary.hard_deadline.strftime('%Y-%m-%d %H:%M')}")
    print(f"Passengers: {itinerary.passengers}")
    
    # Search for options
    print_section("Step 2: Search for Replacement Flights")
    print("Searching...")
    
    options = checkpoint_manager.start_session(itinerary)
    
    print(f"\nFound {len(options)} options:\n")
    
    for i, option in enumerate(options, 1):
        print(f"{i}. {option.airline} {option.flight_number}")
        print(f"   Departure: {option.departure.strftime('%H:%M')}")
        print(f"   Arrival: {option.arrival.strftime('%H:%M')}")
        print(f"   Price: ${option.price:.2f} {option.currency}")
        print(f"   Tradeoff: {option.tradeoff}")
        print(f"   Meets deadline: {'✓' if option.meets_deadline else '✗'}")
        print()
    
    # Select best option
    print_section("Step 3: Select Option")
    
    best_option = options[0]
    print(f"Selecting option: {best_option.airline} {best_option.flight_number}")
    print(f"Price: ${best_option.price:.2f}")
    
    checkpoint = checkpoint_manager.present_initial_booking_checkpoint(best_option)
    
    # Checkpoint 1: Initial Booking
    print_section("Step 4: Checkpoint 1 — Initial Booking Authorization")
    print_checkpoint(checkpoint)
    
    print("User decision: APPROVE")
    success = checkpoint_manager.decide_checkpoint(
        checkpoint.checkpoint_id,
        CheckpointDecision.APPROVE,
        "Looks good, proceed"
    )
    
    if not success:
        print("❌ Checkpoint decision failed")
        return
    
    # Check for additional checkpoints
    state = checkpoint_manager.get_state()
    
    while state['current_checkpoint'] and state['state'] != 'complete':
        current_cp = checkpoint_manager.current_checkpoint
        
        if current_cp.checkpoint_type.value == 'price_change':
            print_section("Step 5: Checkpoint 2 — Price Change")
            print_checkpoint(current_cp)
            print("User decision: APPROVE (accepting price increase)")
            success = checkpoint_manager.decide_checkpoint(
                current_cp.checkpoint_id,
                CheckpointDecision.APPROVE,
                "Accepting the price increase"
            )
        
        elif current_cp.checkpoint_type.value == 'seat_fallback':
            print_section("Step 6: Checkpoint 3 — Seat Fallback")
            print_checkpoint(current_cp)
            print("User decision: APPROVE (accepting auto-assignment)")
            success = checkpoint_manager.decide_checkpoint(
                current_cp.checkpoint_id,
                CheckpointDecision.APPROVE,
                "Auto-assignment is fine"
            )
        
        elif current_cp.checkpoint_type.value == 'final_payment':
            print_section("Step 7: Checkpoint 4 — Final Payment")
            print_checkpoint(current_cp)
            print("User decision: APPROVE (confirming payment)")
            success = checkpoint_manager.decide_checkpoint(
                current_cp.checkpoint_id,
                CheckpointDecision.APPROVE,
                "Confirm payment"
            )
        
        if not success:
            print("❌ Checkpoint decision failed")
            break
        
        state = checkpoint_manager.get_state()
        
        # Small delay to avoid hammering the CLI
        import time
        time.sleep(1)
    
    # Final state
    print_section("Step 8: Booking Complete")
    
    if state['state'] == 'complete':
        print("✅ Ticket issued successfully!")
        print(f"Ticket Number: {state['ticket_number']}")
        print(f"Order ID: {state['order_id']}")
        print(f"Booking ID: {state['booking_id']}")
        print(f"Total Paid: ${state['confirmed_price']:.2f}")
    else:
        print(f"❌ Booking did not complete. Final state: {state['state']}")
    
    # Export audit trail
    print_section("Step 9: Audit Trail")
    
    print(f"Session ID: {audit.session_id}")
    print(f"Total Events: {len(audit.events)}")
    print("\nRecent events:")
    
    for event in audit.events[-10:]:
        print(f"  [{event.timestamp.strftime('%H:%M:%S')}] {event.message}")
    
    print("\n" + "=" * 70)
    print("Exporting audit trail to audit.json...")
    
    with open('audit.json', 'w') as f:
        f.write(audit.export_json())
    
    print("✓ Audit trail exported to audit.json")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
