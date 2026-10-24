#!/usr/bin/env python3
"""
Chaos testing harness for Commerce System Demo.

Scenarios:
1) Kill DB container for a short outage window.
2) Inject DB network latency via Toxiproxy.

The harness drives background traffic (scripts/load_test.py) so existing OTel
dashboards in Grafana receive data during the fault windows.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

TOXIPROXY_API = "http://127.0.0.1:8474"
TOXIPROXY_PROXY_NAME = "commerce_db_proxy"
TOXIC_NAME = "chaos_db_latency"


def _ts() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return _run(["docker", "compose", *args])


def _assert_prerequisites() -> None:
    try:
        _compose("ps")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "docker compose is not available or the current directory is not a compose project"
        ) from exc


def _wait_for_health(base_url: str, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    with httpx.Client(timeout=3.0) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(f"{base_url}/health")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1.0)
    raise RuntimeError(f"API health endpoint did not recover within {timeout_seconds}s")


def _create_latency_toxic(latency_ms: int, jitter_ms: int) -> None:
    payload = {
        "name": TOXIC_NAME,
        "type": "latency",
        "stream": "downstream",
        "toxicity": 1.0,
        "attributes": {"latency": latency_ms, "jitter": jitter_ms},
    }
    with httpx.Client(timeout=5.0) as client:
        delete = client.delete(
            f"{TOXIPROXY_API}/proxies/{TOXIPROXY_PROXY_NAME}/toxics/{TOXIC_NAME}"
        )
        if delete.status_code not in (200, 204, 404):
            raise RuntimeError(
                f"Failed to remove old toxic: {delete.status_code} {delete.text}"
            )
        response = client.post(
            f"{TOXIPROXY_API}/proxies/{TOXIPROXY_PROXY_NAME}/toxics",
            json=payload,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to create latency toxic: {response.status_code} {response.text}"
            )


def _remove_latency_toxic() -> None:
    with httpx.Client(timeout=5.0) as client:
        response = client.delete(
            f"{TOXIPROXY_API}/proxies/{TOXIPROXY_PROXY_NAME}/toxics/{TOXIC_NAME}"
        )
        if response.status_code not in (200, 204, 404):
            raise RuntimeError(
                f"Failed to remove latency toxic: {response.status_code} {response.text}"
            )


def _start_load(url: str, workers: int, duration: int, skip_seed: bool) -> subprocess.Popen[str]:
    script_path = Path(__file__).resolve().parent / "load_test.py"
    cmd = [sys.executable, str(script_path), "--url", url, "--workers", str(workers), "--duration", str(duration)]
    if skip_seed:
        cmd.append("--skip-seed")
    print(f"[{_ts()}] starting load generator: {shlex.join(cmd)}", flush=True)
    return subprocess.Popen(cmd, text=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chaos harness for OTel dashboard validation")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base API URL")
    parser.add_argument("--workers", type=int, default=10, help="Background load workers")
    parser.add_argument("--load-duration", type=int, default=240, help="Load test duration in seconds")
    parser.add_argument("--warmup-seconds", type=int, default=20, help="Warm-up before faults")
    parser.add_argument("--db-outage-seconds", type=int, default=20, help="How long DB stays stopped")
    parser.add_argument("--latency-ms", type=int, default=400, help="Injected DB latency in ms")
    parser.add_argument("--jitter-ms", type=int, default=40, help="Injected latency jitter in ms")
    parser.add_argument(
        "--latency-seconds", type=int, default=40, help="How long latency injection stays active"
    )
    parser.add_argument("--skip-seed", action="store_true", help="Skip initial data seeding")
    args = parser.parse_args()

    _assert_prerequisites()

    print(f"[{_ts()}] chaos run started", flush=True)
    print(f"[{_ts()}] target URL: {args.url}", flush=True)
    print(f"[{_ts()}] expected Grafana: http://127.0.0.1:3000", flush=True)
    print(f"[{_ts()}] expected Prometheus: http://127.0.0.1:9090", flush=True)

    load_proc = _start_load(
        url=args.url,
        workers=args.workers,
        duration=args.load_duration,
        skip_seed=args.skip_seed,
    )

    try:
        print(f"[{_ts()}] warmup {args.warmup_seconds}s", flush=True)
        time.sleep(args.warmup_seconds)

        print(f"[{_ts()}] CHAOS_EVENT db_stop begin (duration={args.db_outage_seconds}s)", flush=True)
        _compose("stop", "db")
        time.sleep(args.db_outage_seconds)
        _compose("start", "db")
        _wait_for_health(args.url)
        print(f"[{_ts()}] CHAOS_EVENT db_stop end (recovered)", flush=True)

        print(
            f"[{_ts()}] CHAOS_EVENT db_latency begin (latency={args.latency_ms}ms, "
            f"jitter={args.jitter_ms}ms, duration={args.latency_seconds}s)",
            flush=True,
        )
        _create_latency_toxic(latency_ms=args.latency_ms, jitter_ms=args.jitter_ms)
        time.sleep(args.latency_seconds)
        _remove_latency_toxic()
        _wait_for_health(args.url)
        print(f"[{_ts()}] CHAOS_EVENT db_latency end (recovered)", flush=True)

        print(f"[{_ts()}] waiting for load generator to complete", flush=True)
        load_proc.wait(timeout=max(args.load_duration, 1) + 30)
    finally:
        try:
            _remove_latency_toxic()
        except Exception:
            pass
        if load_proc.poll() is None:
            load_proc.terminate()
            try:
                load_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                load_proc.kill()

    print("\nChaos run completed.", flush=True)
    print("Correlate fault windows in Grafana dashboards:", flush=True)
    print("- P1 Reliability: request p95, HTTP error rate, in-flight requests, DB query p95", flush=True)
    print("- P3 Diagnostics: latency decomposition, error type panels, app warning/error logs", flush=True)


if __name__ == "__main__":
    main()
