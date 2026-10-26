from __future__ import annotations

import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from flask import Flask, jsonify, render_template

BASE_DIR = Path(__file__).resolve().parent
TARGET_URL = os.getenv("KEEPALIVE_URL", "https://whatsapp-api-nz96.onrender.com/")
INTERVAL_SECONDS = int(os.getenv("KEEPALIVE_INTERVAL", "600"))
NODE_SCRIPT = BASE_DIR / "index.js"

app = Flask(__name__)
state = {
    "last_check": None,
    "last_status": None,
    "last_latency_ms": None,
    "last_error": None,
    "checks": 0,
}
process: Optional[subprocess.Popen] = None
lock = threading.Lock()


def check_target() -> None:
    started = time.perf_counter()
    try:
        response = requests.get(TARGET_URL, timeout=20)
        latency = round((time.perf_counter() - started) * 1000)
        with lock:
            state.update(
                last_check=datetime.now(timezone.utc).isoformat(),
                last_status=response.status_code,
                last_latency_ms=latency,
                last_error=None,
                checks=state["checks"] + 1,
            )
    except requests.RequestException as exc:
        with lock:
            state.update(
                last_check=datetime.now(timezone.utc).isoformat(),
                last_status=None,
                last_latency_ms=None,
                last_error=str(exc),
                checks=state["checks"] + 1,
            )


def keepalive_loop() -> None:
    while True:
        check_target()
        time.sleep(INTERVAL_SECONDS)


def start_gateway() -> None:
    global process
    if process is None or process.poll() is not None:
        process = subprocess.Popen(["node", str(NODE_SCRIPT)], cwd=BASE_DIR)


@app.get("/")
def dashboard():
    return render_template(
        "dashboard.html",
        target_url=TARGET_URL,
        interval=INTERVAL_SECONDS,
        gateway_running=process is not None and process.poll() is None,
    )


@app.get("/api/check")
def manual_check():
    check_target()
    return jsonify({"ok": True})


@app.get("/api/status")
def status():
    with lock:
        snapshot = dict(state)
    snapshot.update(
        target_url=TARGET_URL,
        interval_seconds=INTERVAL_SECONDS,
        gateway_running=process is not None and process.poll() is None,
    )
    return jsonify(snapshot)


if __name__ == "__main__":
    start_gateway()
    threading.Thread(target=keepalive_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
