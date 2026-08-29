#!/usr/bin/env sh
# Restore the Atlas credential, if one was provided, then start the server.
#
# Render's free tier has no shell and no persistent disk, so the interactive
# `atlas-flight auth login` cannot be run there. Setting ATLAS_KEYRING_B64
# (see scripts/export-atlas-credential.sh) puts the credential into the
# container's keyring at boot instead. Without it the app still runs and simply
# reports that flights are unavailable.
set -e

if [ -n "${ATLAS_KEYRING_B64:-}" ]; then
  if python -c '
import base64, json, os, sys
try:
    blob = json.loads(base64.b64decode(os.environ["ATLAS_KEYRING_B64"]))
    import keyring
    keyring.set_password(blob["service"], blob["account"], blob["password"])
except Exception as exc:
    print(f"could not restore the Atlas credential: {type(exc).__name__}: {exc}",
          file=sys.stderr)
    raise SystemExit(1)
'; then
    echo "atlas: credential restored from ATLAS_KEYRING_B64"
  else
    # A bad credential must not stop the app: everything except flights works.
    echo "atlas: credential NOT restored — flights will be unavailable" >&2
  fi
else
  echo "atlas: ATLAS_KEYRING_B64 not set — flights will be unavailable" >&2
fi

exec "$@"
