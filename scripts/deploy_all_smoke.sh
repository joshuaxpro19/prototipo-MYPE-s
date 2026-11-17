#!/usr/bin/env bash
set -uo pipefail

IMAGE=${IMAGE:-mype-all:latest}
NAME=${NAME:-mype-all}
PORT=${PORT:-8092}

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -p "${PORT}:8000" \
  -e DEMO_MODE=1 \
  -e JWT_SECRET=demo-secret \
  -e ADMIN_PASSWORD='Piloto2026!' \
  -e ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP \
  "$IMAGE" >/dev/null

for _ in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/health" || true)
  [ "$code" = "200" ] && break
  sleep 1
done

echo "health : $(curl -s "http://127.0.0.1:${PORT}/health")"
echo "raiz   : $(curl -s -o /dev/null -w '%{http_code} %{content_type}' "http://127.0.0.1:${PORT}/")"
echo "titulo : $(curl -s "http://127.0.0.1:${PORT}/" | grep -o '<title>[^<]*</title>')"
echo "asset  : $(curl -s "http://127.0.0.1:${PORT}/" | grep -o 'assets/[^"]*\.js' | head -1)"
echo "api    : $(curl -s "http://127.0.0.1:${PORT}/api/v1/auth/demo-code")"

OTP=$(curl -s "http://127.0.0.1:${PORT}/api/v1/auth/demo-code" | python3 -c 'import sys,json;print(json.load(sys.stdin)["otp"])')
echo "login  : $(curl -s -X POST "http://127.0.0.1:${PORT}/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"propietario@mype.pe\",\"password\":\"Piloto2026!\",\"otp\":\"${OTP}\"}" | head -c 60)..."
echo "recursos: $(docker stats --no-stream --format 'RAM={{.MemUsage}}' "$NAME")"
