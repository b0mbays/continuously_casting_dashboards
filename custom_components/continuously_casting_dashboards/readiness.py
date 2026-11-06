"""Opt-in dashboard frontend readiness reporting.

A successful CATT command does not prove that the receiving browser has loaded
its custom elements. This tracker receives authenticated Home Assistant service
reports from an optional Lovelace companion card; it never drives recasting.
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit


class ReadinessTracker:
    """Track expected dashboard paths and recent reports per Cast device."""

    def __init__(self, grace_seconds=120, stale_seconds=180):
        self.grace_seconds = grace_seconds
        self.stale_seconds = stale_seconds
        self._sessions = {}

    def cast_started(self, device_name, dashboard_url, enabled=False, now=None):
        """Arm monitoring only for an explicitly opted-in dashboard."""
        if not enabled:
            self._sessions.pop(device_name, None)
            return
        clock = time.monotonic() if now is None else now
        self._sessions[device_name] = {
            "path": urlsplit(dashboard_url).path or "/",
            "started": clock,
            "last_report": None,
            "ready": None,
            "missing_elements": [],
        }

    def report(self, device_name, dashboard_path, ready, missing_elements=(), now=None):
        """Record a report for the expected path; reject unrelated pages.

        Only an authenticated Home Assistant service caller can submit reports;
        the service handler validates active device identity and configuration.
        """
        session = self._sessions.get(device_name)
        if session is None:
            return False
        actual_path = urlsplit(dashboard_path).path or "/"
        if actual_path != session["path"]:
            return False

        clock = time.monotonic() if now is None else now
        session["last_report"] = clock
        session["ready"] = bool(ready)
        session["missing_elements"] = [
            str(tag)[:80] for tag in list(missing_elements)[:10]
            if isinstance(tag, str)
        ]
        return True

    def snapshot(self, device_name, now=None):
        """Return non-sensitive readiness status, without dashboard URLs."""
        session = self._sessions.get(device_name)
        if session is None:
            return {"status": "disabled"}
        clock = time.monotonic() if now is None else now
        last = session["last_report"]
        if last is None:
            age = clock - session["started"]
            return {
                "status": "unconfirmed" if age > self.grace_seconds else "pending",
                "seconds_since_cast": round(max(0, age)),
            }
        age = max(0, clock - last)
        if age > self.stale_seconds:
            status = "stale"
        elif session["ready"]:
            status = "ready"
        else:
            status = "missing_elements"
        return {
            "status": status,
            "seconds_since_report": round(age),
            "missing_elements": list(session["missing_elements"]),
        }

    def clear(self):
        self._sessions.clear()
