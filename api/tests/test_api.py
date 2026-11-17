import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

DB_FILE = ROOT / "data" / "test_api.db"
os.environ["DATABASE_URL"] = "sqlite:///" + str(DB_FILE).replace("\\", "/")
os.environ["ARTIFACTS_DIR"] = str(ROOT / "artifacts")
os.environ["ADMIN_EMAIL"] = "propietario@mype.pe"
os.environ["ADMIN_PASSWORD"] = "Piloto2026!"
os.environ["ADMIN_TOTP_SECRET"] = "JBSWY3DPEHPK3PXP"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient

from app.main import create_app
from app.security import totp_code


@pytest.fixture(scope="session")
def client():
    if DB_FILE.exists():
        try:
            DB_FILE.unlink()
        except PermissionError:
            pass
    with TestClient(create_app()) as c:
        yield c
    if DB_FILE.exists():
        try:
            DB_FILE.unlink()
        except PermissionError:
            pass


@pytest.fixture(scope="session")
def token(client):
    r = client.post("/api/v1/auth/login", json={
        "email": "propietario@mype.pe",
        "password": "Piloto2026!",
        "otp": totp_code("JBSWY3DPEHPK3PXP"),
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": "Bearer " + token}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_rechaza_otp_incorrecto(client):
    r = client.post("/api/v1/auth/login", json={
        "email": "propietario@mype.pe", "password": "Piloto2026!", "otp": "000000"})
    assert r.status_code == 401


def test_login_rechaza_password_incorrecto(client):
    r = client.post("/api/v1/auth/login", json={
        "email": "propietario@mype.pe", "password": "otra", "otp": totp_code("JBSWY3DPEHPK3PXP")})
    assert r.status_code == 401


def test_endpoints_requieren_token(client):
    for path in ("/api/v1/metrics", "/api/v1/forecast", "/api/v1/segments", "/api/v1/purchase-plan"):
        assert client.get(path).status_code == 401, path


def test_dashboard(client, auth):
    r = client.get("/api/v1/dashboard", headers=auth)
    assert r.status_code == 200
    d = r.json()
    assert d["skus_monitoreados"] > 0
    assert "simulad" in d["dataset"]
    assert d["perfil"] == "demo_calibrada"


def test_metrics(client, auth):
    r = client.get("/api/v1/metrics", headers=auth)
    assert r.status_code == 200
    m = r.json()
    assert m["regresion"]["elegido"]
    assert len(m["regresion"]["tabla"]) == 5
    assert len(m["clasificacion"]["tabla"]) == 5


def test_forecast(client, auth):
    r = client.get("/api/v1/forecast?limit=5", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 5
    assert items[0]["pronostico_semana_siguiente"] >= items[-1]["pronostico_semana_siguiente"]

    sku = items[0]["sku_id"]
    one = client.get("/api/v1/forecast/" + sku, headers=auth)
    assert one.status_code == 200
    assert one.json()["sku_id"] == sku
    assert client.get("/api/v1/forecast/SKU-9999", headers=auth).status_code == 404


def test_segments(client, auth):
    r = client.get("/api/v1/segments", headers=auth)
    assert r.status_code == 200
    s = r.json()
    assert s["n_clientes"] > 0
    assert len(s["segmentos"]) == 4
    assert abs(sum(x["pct"] for x in s["segmentos"]) - 100.0) < 1.0


def test_plan_compra(client, auth):
    r = client.get("/api/v1/purchase-plan?top=10", headers=auth)
    assert r.status_code == 200
    p = r.json()
    assert p["n"] == 10
    assert p["costo_total"] > 0
    assert p["items"][0]["pedido_semana"] is not None


def test_flujo_alertas(client, auth):
    sync = client.post("/api/v1/alerts/sync", headers=auth)
    assert sync.status_code == 200
    lista = client.get("/api/v1/alerts", headers=auth)
    assert lista.status_code == 200
    items = lista.json()["items"]
    if items:
        ack = client.post("/api/v1/alerts/%d/ack" % items[0]["id"], headers=auth)
        assert ack.status_code == 200
        assert ack.json()["estado"] == "atendida"
    assert client.post("/api/v1/alerts/999999/ack", headers=auth).status_code == 404
