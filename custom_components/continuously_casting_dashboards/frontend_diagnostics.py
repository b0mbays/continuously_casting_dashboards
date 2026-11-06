"""Privacy-conscious, bounded frontend diagnostics for opted-in Cast sessions."""

from __future__ import annotations

import hashlib
import time
from urllib.parse import urlsplit


def cast_target_token(ip: str) -> str:
    """Create an opaque correlation identifier without exposing receiver IPs."""
    return hashlib.sha256(f"ccd-frontend:{ip}".encode()).hexdigest()[:16]


_PHASES = {"boot", "observing", "reload_requested", "after_reload"}
_DOCUMENT_STATES = {"loading", "interactive", "complete", "unknown"}
_FIELDS = (
    "error_cards",
    "resource_errors",
    "javascript_errors",
    "script_resources",
    "listed_custom_cards",
    "registered_custom_cards",
)


def _small_count(value: object) -> int:
    """Reject non-numeric, negative or oversized metrics from the browser."""
    if isinstance(value, bool):
        return 0
    try:
        return max(0, min(999, int(value)))
    except (ValueError, TypeError, OverflowError):
        return 0


class FrontendDiagnosticsTracker:
    """Keep only non-sensitive browser health counters for active casts."""

    def __init__(self, no_report_seconds: int = 90, stale_seconds: int = 180):
        self.no_report_seconds = no_report_seconds
        self.stale_seconds = stale_seconds
        self._sessions: dict[str, dict] = {}

    def cast_started(
        self,
        device_name: str,
        ip: str,
        dashboard_url: str,
        enabled: bool = False,
        now: float | None = None,
    ) -> None:
        """Arm monitoring when generic Cast recovery is enabled."""
        if not enabled:
            self._sessions.pop(device_name, None)
            return
        self._sessions[device_name] = {
            "token": cast_target_token(ip),
            "path": urlsplit(dashboard_url).path or "/",
            "started": time.monotonic() if now is None else now,
            "last_report": None,
            "phase": None,
            "document_state": "unknown",
            "metrics": {key: 0 for key in _FIELDS},
        }

    def can_accept(self, target: str, dashboard_path: str) -> bool:
        """Whether exactly one active cast matches this reporter identity."""
        if not isinstance(target, str) or not isinstance(dashboard_path, str):
            return False
        path = urlsplit(dashboard_path).path or "/"
        return sum(
            session["token"] == target and session["path"] == path
            for session in self._sessions.values()
        ) == 1

    def report(
        self,
        target: str,
        dashboard_path: str,
        phase: str,
        metrics: dict,
        document_state: str = "unknown",
        now: float | None = None,
    ) -> bool:
        """Accept only a unique active session matching receiver and path."""
        if (
            not isinstance(target, str)
            or not isinstance(dashboard_path, str)
            or not isinstance(metrics, dict)
            or phase not in _PHASES
        ):
            return False
        path = urlsplit(dashboard_path).path or "/"
        matched = [
            session
            for session in self._sessions.values()
            if session["token"] == target and session["path"] == path
        ]
        if len(matched) != 1:
            return False
        session = matched[0]
        session["phase"] = phase
        session["document_state"] = (
            document_state if document_state in _DOCUMENT_STATES else "unknown"
        )
        session["last_report"] = time.monotonic() if now is None else now
        session["metrics"] = {
            key: _small_count(metrics.get(key, 0)) for key in _FIELDS
        }
        return True

    def snapshot(self, device_name: str, now: float | None = None) -> dict:
        """Return a redacted status suitable for HA diagnostics and sensors."""
        session = self._sessions.get(device_name)
        if session is None:
            return {"status": "disabled"}
        clock = time.monotonic() if now is None else now
        last = session["last_report"]
        if last is None:
            age = max(0, clock - session["started"])
            return {
                "status": "no_report" if age >= self.no_report_seconds else "awaiting_report",
                "seconds_since_cast": round(age),
            }
        age = max(0, clock - last)
        metrics = dict(session["metrics"])
        if age >= self.stale_seconds:
            status = "stale"
        elif session["phase"] == "reload_requested":
            status = "reload_requested"
        elif metrics["error_cards"]:
            status = "error_cards"
        elif metrics["resource_errors"] or metrics["javascript_errors"]:
            status = "script_or_resource_errors"
        else:
            status = "observed"
        return {
            "status": status,
            "phase": session["phase"],
            "document_state": session["document_state"],
            "seconds_since_report": round(age),
            **metrics,
        }

    def clear(self) -> None:
        self._sessions.clear()
