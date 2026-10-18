#!/usr/bin/env bash
# Create or update the RetailNova Model Armor template (idempotent).
# Default: projects/retailnova-ai/locations/asia-south1/templates/retailnova-shield
# Filters: prompt injection / jailbreak and responsible-AI (hate speech, harassment, sexually explicit,
# dangerous content) at MEDIUM_AND_ABOVE, plus the malicious-URI filter where the region supports it
# (asia-south1 does not; us-central1 does). Re-running updates the filters in place.
# Usage: source scripts/env.sh && bash scripts/model_armor_template.sh
#        MODEL_ARMOR_LOCATION=us-central1 bash scripts/model_armor_template.sh
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-retailnova-ai}"
LOC="${MODEL_ARMOR_LOCATION:-asia-south1}"
TEMPLATE_ID="${MODEL_ARMOR_TEMPLATE_ID:-retailnova-shield}"
LEVEL="${MODEL_ARMOR_LEVEL:-MEDIUM_AND_ABOVE}"
BASE="https://modelarmor.${LOC}.rep.googleapis.com/v1/projects/${PROJECT}/locations/${LOC}/templates"
TOKEN="$(gcloud auth print-access-token)"
AUTH=(-H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json")
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

body() {  # $1 = include malicious URI filter (1/0)
  local uri=""
  [ "$1" = "1" ] && uri='"maliciousUriFilterSettings": {"filterEnforcement": "ENABLED"},'
  cat <<JSON
{
  "filterConfig": {
    "piAndJailbreakFilterSettings": {"filterEnforcement": "ENABLED", "confidenceLevel": "${LEVEL}"},
    ${uri}
    "raiSettings": {
      "raiFilters": [
        {"filterType": "HATE_SPEECH", "confidenceLevel": "${LEVEL}"},
        {"filterType": "HARASSMENT", "confidenceLevel": "${LEVEL}"},
        {"filterType": "SEXUALLY_EXPLICIT", "confidenceLevel": "${LEVEL}"},
        {"filterType": "DANGEROUS", "confidenceLevel": "${LEVEL}"}
      ]
    }
  }
}
JSON
}

EXISTS=$(curl -s -o /dev/null -w '%{http_code}' "${AUTH[@]}" "${BASE}/${TEMPLATE_ID}")
case "$EXISTS" in
  404) METHOD=POST; URL="${BASE}?templateId=${TEMPLATE_ID}" ;;
  200) METHOD=PATCH; URL="${BASE}/${TEMPLATE_ID}?updateMask=filterConfig" ;;
  *) echo "Unexpected status ${EXISTS} reading ${BASE}/${TEMPLATE_ID}" >&2; exit 1 ;;
esac

echo "${METHOD} template ${TEMPLATE_ID} in ${LOC} (with malicious-URI filter)..." >&2
CODE=$(curl -s -o "$TMP" -w '%{http_code}' -X "$METHOD" "${AUTH[@]}" "$URL" -d "$(body 1)")
if [ "$CODE" = "400" ] && grep -q "Malicious URI filter" "$TMP"; then
  echo "Region ${LOC} has no malicious-URI filter; applying the other filters only." >&2
  CODE=$(curl -s -o "$TMP" -w '%{http_code}' -X "$METHOD" "${AUTH[@]}" "$URL" -d "$(body 0)")
fi
if [ "$CODE" != "200" ]; then
  echo "Template ${METHOD} failed (HTTP ${CODE}):" >&2
  cat "$TMP" >&2
  exit 1
fi

curl -sf "${AUTH[@]}" "${BASE}/${TEMPLATE_ID}"
echo
echo "MODEL_ARMOR_TEMPLATE=projects/${PROJECT}/locations/${LOC}/templates/${TEMPLATE_ID}" >&2
