"""Inspect VM Compose isolation or probe tokenless MAX HTTPS from worker.

The egress mode issues one GET without MAX Authorization; it never sends a bot
message. CI passes synthetic production settings only to validate the network.
"""

from __future__ import annotations

import json
import socket
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def verify_restarts(config: dict) -> None:
    services = config["services"]
    for name in ("db", "api", "worker", "web"):
        assert services[name].get("restart") == "unless-stopped", (name, services[name].get("restart"))
    # Alembic is a one-shot prerequisite, never a daemon to restart indefinitely.
    assert services["migrate"].get("restart") in (None, "no")
    print("E4 persistent service restart policies: OK")


def verify_config() -> None:
    config = json.load(sys.stdin)
    verify_restarts(config)
    services = config["services"]
    expected = {
        "db": {"private"},
        "migrate": {"private"},
        "api": {"private", "model_egress"},
        "worker": {"private", "max_egress"},
        "web": {"private", "edge"},
    }
    for name, networks in expected.items():
        service = services[name]
        assert set(service["networks"]) == networks, (name, service["networks"])
        assert not service.get("ports"), f"{name} publishes a port"
    networks = config["networks"]
    assert networks["private"]["internal"] is True
    assert not networks["model_egress"].get("internal", False)
    assert not networks["max_egress"].get("internal", False)
    assert networks["edge"]["external"] is True
    assert networks["edge"]["name"] == "vk-zhkh-edge"
    for name in ("migrate", "api", "worker"):
        env = services[name]["environment"]
        assert env["APP_MODE"] == "production"
        assert env["ENGINE_MODE"] == "real"
        assert env["DEMO_AUTH_ENABLED"] == "false"
        assert not env["DEMO_ACCESS_CODE"]
        for key in ("MAX_BOT_TOKEN", "MAX_WEBHOOK_SECRET", "MAX_WEB_APP"):
            assert env[key], (name, key)
    print("E4 VM Compose isolation and production settings: OK")


def verify_egress() -> None:
    host = "platform-api2.max.ru"
    assert socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    request = Request(f"https://{host}/", method="GET")
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
    except HTTPError as error:
        status = error.code
    assert 100 <= status < 600
    print("E4 worker DNS and tokenless HTTPS GET: OK")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"config", "restart", "egress"}:
        raise SystemExit("usage: verify_e4_vm_network.py config|restart|egress")
    if sys.argv[1] == "config":
        verify_config()
    elif sys.argv[1] == "restart":
        verify_restarts(json.load(sys.stdin))
    else:
        verify_egress()
