#!/usr/bin/env bash
set -uo pipefail

IMAGE=${IMAGE:-mype-demo:latest}
NAME=${NAME:-mype-demo}
PORT=${PORT:-8090}

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -p "${PORT}:8000" \
  -e DEMO_MODE=1 \
  -e JWT_SECRET=demo-secret \
  -e ADMIN_PASSWORD='Piloto2026!' \
  -e ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP \
  -e ALERT_THRESHOLD=0.5 \
  "$IMAGE" >/dev/null

for _ in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/health" || true)
  [ "$code" = "200" ] && break
  sleep 1
done

echo "health   : $(curl -s "http://127.0.0.1:${PORT}/health")"
echo "demo-code: $(curl -s "http://127.0.0.1:${PORT}/api/v1/auth/demo-code")"

OTP=$(curl -s "http://127.0.0.1:${PORT}/api/v1/auth/demo-code" | python3 -c 'import sys,json;print(json.load(sys.stdin)["otp"])')
TOKEN=$(curl -s -X POST "http://127.0.0.1:${PORT}/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"propietario@mype.pe\",\"password\":\"Piloto2026!\",\"otp\":\"${OTP}\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

echo "login    : ${TOKEN:0:24}..."
echo "dashboard: $(curl -s -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:${PORT}/api/v1/dashboard" | head -c 420)"
echo "modelos  : $(curl -s -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:${PORT}/api/v1/models")"
echo "recursos : $(docker stats --no-stream --format 'RAM={{.MemUsage}} CPU={{.CPUPerc}}' "$NAME")"
