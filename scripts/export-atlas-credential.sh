#!/usr/bin/env bash
# Export the Atlas credential from this Mac's Keychain as one env-var value.
#
# Why this exists: the Atlas CLI is authorised through an interactive browser
# flow and keeps the result in an OS keyring. Render's free tier has no shell,
# so that login cannot be performed on the server. This moves the credential
# you already hold into a Render environment variable instead.
#
# The value is printed to your terminal only. Nothing is uploaded, and the
# secret never enters the repo or the Docker image.
#
# Usage:
#   ./scripts/export-atlas-credential.sh
#   # copy the output, paste it into Render as ATLAS_KEYRING_B64
set -euo pipefail

SERVICE="atlas-flight-booking"

if ! command -v security >/dev/null 2>&1; then
  echo "This script reads the macOS Keychain and only runs on macOS." >&2
  echo "On Linux, export the entry from your keyring manually." >&2
  exit 1
fi

ACCOUNT="$(security find-generic-password -s "$SERVICE" 2>/dev/null \
  | awk -F'"' '/"acct"<blob>=/{print $4}' | head -1)"

if [ -z "$ACCOUNT" ]; then
  echo "No '$SERVICE' entry in your Keychain." >&2
  echo "Log in first:  atlas-flight auth login --json" >&2
  exit 1
fi

# -w prints only the secret. macOS will prompt for permission the first time.
PASSWORD="$(security find-generic-password -s "$SERVICE" -a "$ACCOUNT" -w)"

python3 - "$SERVICE" "$ACCOUNT" "$PASSWORD" <<'PY'
import base64, json, sys
service, account, password = sys.argv[1], sys.argv[2], sys.argv[3]
blob = json.dumps({"service": service, "account": account, "password": password})
print(base64.b64encode(blob.encode()).decode())
PY

cat >&2 <<'NOTE'

Copy the single line above and set it in Render as:

    ATLAS_KEYRING_B64

Treat it like a password: it authorises bookings on your Atlas account.
Anyone who can read your Render environment can use it. Rotate it by running
`atlas-flight auth login` again and re-running this script.
NOTE
