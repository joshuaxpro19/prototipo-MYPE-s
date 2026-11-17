import json
import time
import urllib.error
import urllib.request


class MlflowRest:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def _call(self, path, payload=None):
        url = self.base + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                body = res.read().decode()
                return json.loads(body) if body else {}
        except (urllib.error.URLError, TimeoutError, ValueError):
            return None

    def experiment(self, name):
        got = self._call("/api/2.0/mlflow/experiments/get-by-name?experiment_name=" + name)
        if got and "experiment" in got:
            return got["experiment"]["experiment_id"]
        created = self._call("/api/2.0/mlflow/experiments/create", {"name": name})
        return created["experiment_id"] if created else None

    def run(self, experiment_name, params, metrics, tags=None):
        exp = self.experiment(experiment_name)
        if exp is None:
            return None
        started = self._call("/api/2.0/mlflow/runs/create", {
            "experiment_id": exp,
            "start_time": int(time.time() * 1000),
            "tags": [{"key": k, "value": str(v)} for k, v in (tags or {}).items()],
        })
        if not started:
            return None
        run_id = started["run"]["info"]["run_id"]
        for k, v in params.items():
            self._call("/api/2.0/mlflow/runs/log-parameter", {"run_id": run_id, "key": k, "value": str(v)})
        for k, v in metrics.items():
            if v is not None:
                self._call("/api/2.0/mlflow/runs/log-metric", {"run_id": run_id, "key": k, "value": float(v), "timestamp": int(time.time() * 1000), "step": 0})
        self._call("/api/2.0/mlflow/runs/update", {"run_id": run_id, "status": "FINISHED", "end_time": int(time.time() * 1000)})
        return run_id
