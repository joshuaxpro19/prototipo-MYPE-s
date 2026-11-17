import logging
import os
import sys
import time

from apscheduler.schedulers.blocking import BlockingScheduler

from .db import audit, init_db, make_engine
from .main import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(levelname)s %(message)s")
log = logging.getLogger("worker")


HEARTBEAT = os.environ.get("WORKER_HEARTBEAT", "/tmp/worker.alive")


def beat():
    with open(HEARTBEAT, "w", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S"))


def sync_once():
    beat()
    engine = make_engine()
    init_db(engine, os.environ.get("ADMIN_EMAIL", "propietario@mype.pe"),
            os.environ.get("ADMIN_PASSWORD", "Piloto2026!"),
            os.environ.get("ADMIN_TOTP_SECRET", "JBSWY3DPEHPK3PXP"))
    app = create_app()
    for route in app.routes:
        if getattr(route, "path", "") == "/api/v1/alerts/sync":
            res = route.endpoint(actor={"sub": "worker", "role": "sistema"})
            beat()
            log.info("alertas sincronizadas: %s", res)
            return res
    with engine.begin() as conn:
        conn.execute(audit.insert().values(ts=time.strftime("%Y-%m-%d %H:%M:%S"), actor="worker", accion="sin_ruta", detalle="no se encontro sync"))
    return None


def main():
    interval = int(os.environ.get("SYNC_INTERVAL_MIN", "60"))
    sync_once()
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(sync_once, "interval", minutes=interval, id="sync_alertas", max_instances=1,
                  coalesce=True, misfire_grace_time=max(600, interval * 60))
    log.info("worker iniciado, intervalo %s min", interval)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)


if __name__ == "__main__":
    main()
