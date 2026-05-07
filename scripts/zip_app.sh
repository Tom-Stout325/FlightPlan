#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: ./scripts/zip_app.sh <app_name>"
  echo "Example: ./scripts/zip_app.sh airspace"
  exit 1
fi

APP_NAME="$1"
APP_PATH="./${APP_NAME}"
OUTPUT="${APP_NAME}.zip"

VALID_APPS=(
  accounts
  airspace
  clients
  documents
  equipment
  flightlogs
  money
  operations
  pilot
)

is_valid=false
for app in "${VALID_APPS[@]}"; do
  if [ "$APP_NAME" = "$app" ]; then
    is_valid=true
    break
  fi
done

if [ "$is_valid" = false ]; then
  echo "Error: '$APP_NAME' is not one of the supported apps."
  echo "Supported apps: ${VALID_APPS[*]}"
  exit 1
fi

if [ ! -d "$APP_PATH" ]; then
  echo "Error: App folder not found: $APP_PATH"
  exit 1
fi

rm -f "$OUTPUT"

zip -r "$OUTPUT" "$APP_NAME" \
  -x "*/__pycache__/*" \
  -x "*.pyc" \
  -x "*.pyo" \
  -x "*.DS_Store" \
  -x "__MACOSX/*"


echo "Created $OUTPUT"
