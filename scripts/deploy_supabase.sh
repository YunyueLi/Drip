#!/usr/bin/env bash
# One-shot deploy of Drip's backend to YOUR Supabase project.
#
#   bash scripts/deploy_supabase.sh
#
# It will: authenticate (browser, once) → link the project → create the tables
# → deploy the three Edge Functions → set the non-secret function config.
# The only things it asks YOU for: authorize in the browser, and your project's
# database password (the one you set when creating the project).
#
# Secrets stay on your machine / in Supabase — never in this repo or chat.
set -euo pipefail

REF="xneuizhnnzsvbbjirhdw"
APP_URL="https://yunyueli.github.io/Drip/app.html"
REDIRECT="https://${REF}.supabase.co/functions/v1/meta-oauth"
cd "$(dirname "$0")/.."

command -v supabase >/dev/null || { echo "supabase CLI not found. Install: brew install supabase/tap/supabase"; exit 1; }

# ── auth: token file (CI/non-interactive) or interactive browser login ───────
if [ -s .supabase-token ]; then
  export SUPABASE_ACCESS_TOKEN="$(tr -d '[:space:]' < .supabase-token)"
  echo "▸ using access token from .supabase-token"
elif ! supabase projects list >/dev/null 2>&1; then
  echo "▸ opening browser to authorize Supabase (click Authorize, paste the code back here)…"
  supabase login
fi

echo "▸ linking project ${REF} (you'll be asked for the project DB password)…"
supabase link --project-ref "$REF"

echo "▸ creating tables (ad_connections / oauth_states / drip_audit)…"
supabase db push

echo "▸ deploying Edge Functions…"
supabase functions deploy meta-oauth ads-pull ads-apply

echo "▸ setting non-secret function config…"
supabase secrets set "APP_URL=${APP_URL}" "META_REDIRECT_URI=${REDIRECT}"

echo
echo "✅ Backend deployed to https://${REF}.supabase.co"
supabase functions list || true
echo
echo "NEXT (for auto-connecting Meta — dev mode, no review needed for your own account):"
echo "  1) developers.facebook.com → create app → add Marketing API → Facebook Login."
echo "  2) OAuth redirect URI: ${REDIRECT}"
echo "  3) supabase secrets set META_APP_ID=<id> META_APP_SECRET=<secret>"
echo "  Then: app.html → Settings → Connectors → Connect Meta."
