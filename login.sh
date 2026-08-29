#!/bin/bash
# Simple Atlas login helper

export PATH="$HOME/.local/bin:$PATH"

echo "Getting authorization URL..."

# Get the login response and extract URL
RESPONSE=$(atlas-flight auth login --json 2>&1)
URL=$(echo "$RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['data']['authorization_url'])" 2>/dev/null)

if [ -z "$URL" ]; then
    echo "Error: Could not get authorization URL"
    echo "$RESPONSE"
    exit 1
fi

echo ""
echo "Opening browser for login..."
echo ""

# Open in default browser (macOS)
open "$URL"

echo "✓ Browser opened"
echo ""
echo "After completing login in the browser, run:"
echo "  atlas-flight auth poll --json"
echo ""
echo "Or use this to auto-poll:"
echo "  while ! atlas-flight auth status --json | grep -q '\"authenticated\":true'; do echo 'Polling...'; sleep 2; atlas-flight auth poll --json; done"
