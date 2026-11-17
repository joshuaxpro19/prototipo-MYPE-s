import os

from sqlalchemy import (Column, DateTime, Float, Integer, MetaData, String, Table,
                        create_engine, select, text, update)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .security import hash_password, verify_password

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(120), unique=True, nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("totp_secret", String(64), nullable=False),
    Column("role", String(20), nullable=False, default="propietario"),
    Column("activo", Integer, nullable=False, default=1),
)

alerts = Table(
    "alerts", metadata,
    Column("id", Integer, primary_key=True),
    Column("sku_id", String(20), nullable=False),
    Column("prob_quiebre", Float, nullable=False),
    Column("severidad", String(20), nullable=False),
    Column("tipo", String(20)),
    Column("detalle", String(200)),
    Column("estado", String(20), nullable=False, default="abierta"),
    Column("creado", DateTime, nullable=False),
    Column("atendido_por", String(120)),
)

audit = Table(
    "audit", metadata,
    Column("id", Integer, primary_key=True),
    Column("ts", DateTime, nullable=False),
    Column("actor", String(120), nullable=False),
    Column("accion", String(80), nullable=False),
    Column("detalle", String(500)),
)


def make_engine(url=None):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///./data/app.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite:///./data"):
        os.makedirs(os.path.dirname(url.replace("sqlite:///", "")), exist_ok=True)
    return create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)


def init_db(engine, seed_email, seed_password, seed_totp):
    metadata.create_all(engine)
    with engine.begin() as conn:
        for ddl in ("ALTER TABLE alerts ADD COLUMN tipo VARCHAR(20)",
                    "ALTER TABLE alerts ADD COLUMN detalle VARCHAR(200)"):
            try:
                conn.execute(text(ddl))
            except Exception:
                pass
    with engine.begin() as conn:
        row = conn.execute(select(users).where(users.c.email == seed_email)).mappings().first()
        if not row:
            conn.execute(users.insert().values(
                email=seed_email,
                password_hash=hash_password(seed_password),
                totp_secret=seed_totp,
                role="propietario",
                activo=1,
            ))
        elif (not verify_password(seed_password, row["password_hash"])
              or row["totp_secret"] != seed_totp or not row["activo"]):
            conn.execute(update(users).where(users.c.email == seed_email).values(
                password_hash=hash_password(seed_password), totp_secret=seed_totp, activo=1))
