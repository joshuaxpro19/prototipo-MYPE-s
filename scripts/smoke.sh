#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== health via nginx =="
curl -s http://localhost:8080/health; echo

echo "== 401 sin token =="
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/dashboard

OTP=$(docker compose exec -T api python -m app.totp | tr -d '\r\n')
echo "== login con OTP =="
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"propietario@mype.pe\",\"password\":\"Piloto2026!\",\"otp\":\"$OTP\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
echo "token emitido: ${TOKEN:0:24}..."

echo "== dashboard =="
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/dashboard; echo

echo "== forecast top 3 =="
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8080/api/v1/forecast?limit=3"; echo

echo "== plan de compra (1 SKU) =="
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8080/api/v1/purchase-plan?top=1"; echo

echo "== alertas en postgres =="
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/alerts \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['n'],'alertas abiertas');print(d['items'][0] if d['items'] else 'ninguna')"

echo "== frontend =="
curl -s http://localhost:8080/ | head -c 130; echo
