sdk: docker
app_port: 8000
title: Prototipo MYPE (demo calibrada)
emoji: 🏪
colorFrom: blue
colorTo: indigo
pinned: false
---

# Prototipo MYPE - API

Demo local convertida en demo pública. Los datos son sintéticos y los parámetros del
simulador se ajustaron para acercar las métricas al informe; no son mediciones de un piloto real.

- `DEMO_MODE=1` habilita `GET /api/v1/auth/demo-code` para entrar sin calculadora TOTP.
- Persistencia en SQLite dentro del contenedor: los usuarios y alertas se reinician con la instancia.
- Artefactos (modelos XGBoost y K-Means) van incluidos en la imagen, en `/srv/artifacts`.
