#!/usr/bin/env bash
set -euo pipefail

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
API_URL="${API_URL:-http://localhost:8000/api/v1}"

TOKEN_RESPONSE="$(curl -fsS \
  -d "client_id=ticketlog-web" \
  -d "username=citizen1" \
  -d "password=citizen-password" \
  -d "grant_type=password" \
  "${KEYCLOAK_URL}/realms/ticketlog/protocol/openid-connect/token")"

ACCESS_TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' <<< "${TOKEN_RESPONSE}")"

TICKET_RESPONSE="$(curl -fsS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"title":"Smoke test complaint","category":"operations","description":"This smoke test verifies authenticated ticket submission."}' \
  "${API_URL}/tickets")"

TICKET_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<< "${TICKET_RESPONSE}")"

curl -fsS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "${API_URL}/tickets/${TICKET_ID}/analyses" >/dev/null

echo "Smoke test passed for ticket ${TICKET_ID}"
