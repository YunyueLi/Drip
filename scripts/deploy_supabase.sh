#!/usr/bin/env bash
# One-shot, TOKEN-ONLY deploy of Drip's backend to YOUR Supabase project.
# No DB password, no browser dance — just a personal access token.
#
#   echo "sbp_xxx" > .supabase-token   # Supabase → avatar → Access Tokens → Generate
#   bash scripts/deploy_supabase.sh
#
# Does: create tables via the Management API (DDL with the token, no DB password)
#       → deploy the 3 Edge Functions → set non-secret function config.
# Secrets stay on your machine / in Supabase — never in this repo or chat.
set -euo pipefail

REF="xneuizhnnzsvbbjirhdw"
APP_URL="https://yunyueli.github.io/Drip/app.html"
REDIRECT="https://${REF}.supabase.co/functions/v1/meta-oauth"
MIGRATION="supabase/migrations/20260610120000_drip_live.sql"
cd "$(dirname "$0")/.."

[ -s .supabase-token ] && export SUPABASE_ACCESS_TOKEN="$(tr -d '[:space:]' < .supabase-token)"
: "${SUPABASE_ACCESS_TOKEN:?need a token — put it in .supabase-token (Supabase → Access Tokens)}"
TOKEN="$SUPABASE_ACCESS_TOKEN"
command -v supabase >/dev/null || { echo "supabase CLI missing: brew install supabase/tap/supabase"; exit 1; }

echo "▸ creating tables via Management API (no DB password needed)…"
BODY="$(node -e 'process.stdout.write(JSON.stringify({query:require("fs").readFileSync(process.argv[1],"utf8")}))' "$MIGRATION")"
HTTP="$(curl -s -o /tmp/drip_ddl.out -w '%{http_code}' -X POST \
  "https://api.supabase.com/v1/projects/${REF}/database/query" \
  -H "Authorization: Bearer ${TOKEN}" -H "content-type: application/json" -d "$BODY")"
if [ "$HTTP" = "200" ] || [ "$HTTP" = "201" ]; then echo "  ✓ tables ready"; else echo "  ✗ DDL failed ($HTTP): $(cat /tmp/drip_ddl.out)"; exit 1; fi

echo "▸ deploying Edge Functions (token only, no link/DB password)…"
supabase functions deploy meta-oauth ads-pull ads-apply --project-ref "$REF"

echo "▸ setting non-secret function config…"
supabase secrets set "APP_URL=${APP_URL}" "META_REDIRECT_URI=${REDIRECT}" --project-ref "$REF"

echo
echo "▸ verifying functions are live on cloud + auth gate works…"
PUBKEY="sb_publishable_QjqFx1bgU9nyWzQs2VXjLg_8YTWM7FI"
FB="https://${REF}.supabase.co/functions/v1"
ok=1
for fn in ads-pull ads-apply; do
  c="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$FB/$fn" -H "apikey: $PUBKEY" -H "content-type: application/json" -d '{}')"
  printf "  %-10s no-auth → %s  (expect 401)" "$fn" "$c"; [ "$c" = "401" ] && echo "  ✓" || { echo "  ✗"; ok=0; }
done
c="$(curl -s -o /dev/null -w '%{http_code}' "$FB/meta-oauth" -H "apikey: $PUBKEY")"
printf "  %-10s no-auth → %s  (expect 401)" "meta-oauth" "$c"; [ "$c" = "401" ] && echo "  ✓" || { echo "  ✗"; ok=0; }
[ "$ok" = "1" ] && echo "  ✅ all three functions deployed, responding, and gating unauthenticated calls" || echo "  ⚠ unexpected codes — check 'supabase functions list' / logs"
echo
echo "✅ Backend deployed → ${FB}/{meta-oauth,ads-pull,ads-apply}"
echo "NEXT (Meta, dev mode — your own account, no review):"
echo "  developers.facebook.com → app + Marketing API + Facebook Login"
echo "  OAuth redirect: ${REDIRECT}"
echo "  supabase secrets set META_APP_ID=<id> META_APP_SECRET=<secret> --project-ref ${REF}"
