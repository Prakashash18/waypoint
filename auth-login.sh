#!/bin/bash
# Helper script to login to Atlas and open the authorization URL

set -e

export PATH="$HOME/.local/bin:$PATH"

echo "Starting Atlas authentication..."
echo ""

# Get the login response
RESPONSE=$(atlas-flight auth login --json 2>&1)

# Extract the authorization URL
URL=$(echo "$RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['data']['authorization_url'])")

# Extract expiration time
EXPIRES=$(echo "$RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['data']['expires_at'])")

echo "Authorization URL:"
echo "$URL"
echo ""
echo "Expires at: $EXPIRES"
echo ""

# Try to open the URL in the default browser
if command -v open &> /dev/null; then
    echo "Opening browser..."
    open "$URL"
elif command -v xdg-open &> /dev/null; then
    echo "Opening browser..."
    xdg-open "$URL"
else
    echo "Please open the URL above in your browser manually"
fi

echo ""
echo "After completing login in the browser, run:"
echo "  atlas-flight auth poll"
echo ""
echo "Or run this to poll automatically:"
echo "  watch -n 2 'atlas-flight auth poll --json'"
