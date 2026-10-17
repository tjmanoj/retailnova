# RetailNova environment. Run `source scripts/env.sh` before any cloud command.
# This keeps gcloud, ADC and the Python SDKs on the PERSONAL account (manojtofficial@gmail.com)
# without touching the work gcloud config in ~/.config/gcloud. No secrets live here.
export CLOUDSDK_CONFIG="$HOME/.config/gcloud-retailnova"
export GOOGLE_APPLICATION_CREDENTIALS="$CLOUDSDK_CONFIG/application_default_credentials.json"
export GOOGLE_CLOUD_PROJECT="retailnova-ai"
export GOOGLE_CLOUD_LOCATION="global"          # Gemini endpoint on Agent Platform
export GOOGLE_GENAI_USE_VERTEXAI="TRUE"
export REGION="asia-south1"                     # Cloud Run, Firestore, BigQuery, Artifact Registry
export BQ_DATASET="retailnova"
export PATH="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)/.venv/bin:$PATH"

_acct="$(gcloud config get account 2>/dev/null)"
if [ "$_acct" != "manojtofficial@gmail.com" ]; then
  echo "WARNING: gcloud account is '$_acct' (expected manojtofficial@gmail.com)" >&2
fi
unset _acct
