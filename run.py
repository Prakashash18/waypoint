#!/usr/bin/env python3
"""
Waypoint — Disruption Rebooking Agent
Main entry point
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.ui.app import app

if __name__ == '__main__':
    print("🛫 Waypoint — Disruption Rebooking Agent")
    print("=" * 50)
    print("Starting server on http://localhost:2000")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=2000)
