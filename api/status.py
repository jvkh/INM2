"""Status endpoint for the API and collector."""

import logging
import os
from typing import Any
from pathlib import Path

from fastapi import APIRouter, Request

from common.env import EnvConfig
from common.status import CollectorStatus


logger = logging.getLogger(__name__)
router = APIRouter()
HONEYPOT_STATE_FILE = Path(os.environ.get("HONEYPOT_STATE_PATH", "/logs/honeypot.state"))
HONEYPOT_CONFIG_FILE = Path(os.environ.get("HONEYPOT_CONFIG_FILE", "/honeypot-config/.env"))
HONEYPOT_ENVIRONMENT_KEYS = (
    "HONEYPOT_ENABLED",
    "HONEYPOT_HOST",
    "TRAEFIK_DOCKER_NETWORK",
    "HONEYPOT_HTTP_ENTRYPOINT",
    "HONEYPOT_ENTRYPOINT",
    "HONEYPOT_CERT_RESOLVER",
    "HONEYPOT_UID",
    "HONEYPOT_GID",
)


def _read_honeypot_config() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in HONEYPOT_CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key.strip()] = value.split("#", 1)[0].strip().strip("\"'").strip()
    except OSError:
        pass
    return values


def _honeypot_is_running() -> bool:
    try:
        return HONEYPOT_STATE_FILE.read_text(encoding="ascii").strip() == "running"
    except OSError:
        return False


def _honeypot_is_configured() -> bool:
    """Return the explicit visibility switch, or infer legacy configurations."""
    # The main INM2 Compose project may provide the switch from its root .env.
    # An empty Compose interpolation means no override; in that case read the
    # optional Honeypot subproject config mounted into the API container.
    environment_enabled = os.environ.get("HONEYPOT_ENABLED", "").strip()
    if environment_enabled:
        return environment_enabled.lower() in {"1", "true", "yes", "on"}
    values = _read_honeypot_config()
    enabled = values.get("HONEYPOT_ENABLED")
    if enabled is not None:
        return enabled.lower() in {"1", "true", "yes", "on"}
    # Before the switch existed, a hostname in the config implied enabled.
    return bool(values.get("HONEYPOT_HOST"))


@router.get("/status")
def get_status(request: Request) -> dict[str, Any]:
    """Report API health, stored collector status, and safe configuration."""
    fallback = {
        "status": "degraded",
        "database": "unavailable",
        "collector_status": {
            "available": False,
            "last_import": None,
            "activity": "Unknown",
            "import_file": "",
            "last_import_file": "",
            "import_count": 0,
        },
        "environment": {
            "COWRIE_ENABLED": os.environ.get("COWRIE_ENABLED", "false"),
            "COWRIE_LOG_PATH": os.environ.get("COWRIE_LOG_PATH", "/cowrie-logs/cowrie.json"),
        },
        "honeypot_available": False,
        "honeypot_configured": _honeypot_is_configured(),
        "cowrie_configured": os.environ.get("COWRIE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
    }
    try:
        database = request.app.state.database
        if database is None:
            return fallback

        database.query("SELECT 1")
        collector_status = CollectorStatus.read_snapshot(database)
        stored_environment = collector_status.pop("environment", {})
        environment = {
            name: value
            for name, value in stored_environment.items()
            if name in EnvConfig.DEFAULTS
            and name != "INM2_COLLECTOR_PORT"
            and not any(token in name.upper() for token in ("SECRET", "PASSWORD", "TOKEN"))
        }
        if _honeypot_is_configured():
            honeypot_environment = _read_honeypot_config()
            honeypot_environment.update({
                name: os.environ[name]
                for name in HONEYPOT_ENVIRONMENT_KEYS
                if os.environ.get(name)
            })
            environment.update({
                name: honeypot_environment[name]
                for name in HONEYPOT_ENVIRONMENT_KEYS
                if honeypot_environment.get(name)
            })
        # These settings are injected directly by Compose rather than EnvConfig.
        for name, default in (("COWRIE_ENABLED", "false"), ("COWRIE_LOG_PATH", "/cowrie-logs/cowrie.json")):
            environment[name] = os.environ.get(name, "").strip() or environment.get(name, default)
        # The API and collector receive the same Compose setting. Prefer the
        # enabled value if either container has it, so a stale API value does
        # not hide a collector that is already configured for Cowrie.
        api_cowrie_enabled = os.environ.get("COWRIE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        collector_cowrie_enabled = str(stored_environment.get("COWRIE_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
        cowrie_configured = api_cowrie_enabled or collector_cowrie_enabled
        environment["COWRIE_ENABLED"] = "true" if cowrie_configured else "false"
        collector_status["available"] = True
        return {
            "status": "ok",
            "database": "ok",
            "collector_status": collector_status,
            "environment": environment,
            "honeypot_available": _honeypot_is_running(),
            "honeypot_configured": _honeypot_is_configured(),
            "cowrie_configured": cowrie_configured,
        }
    except Exception:
        logger.exception("Could not read API status")
        return fallback
