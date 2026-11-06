"""Small, Home Assistant-independent reliability helpers for Cast devices."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Iterable

# Prefix matching is deliberately restricted to Google's observed suffix.
# Generic startswith() would confuse similarly named displays.
_GOOGLE_SUFFIX = re.compile(r"^(.+?)\s+-\s+Google Inc\.\s+Google\s+.+$", re.I)


def match_discovered_device(
    requested_name: str, discovered: Iterable[tuple[str, str]]
) -> str | None:
    """Return a unique, safe IP match or None when names are ambiguous.

    Exact names win over Google's appended manufacturer/model suffix; every
    matching candidate must resolve to one IP address.
    """
    requested = requested_name.strip().casefold()
    if not requested:
        return None

    candidates = list(discovered)
    exact = {ip for name, ip in candidates if name.strip().casefold() == requested}
    if exact:
        return next(iter(exact)) if len(exact) == 1 else None

    suffixed = set()
    for name, ip in candidates:
        match = _GOOGLE_SUFFIX.fullmatch(name.strip())
        if match and match.group(1).strip().casefold() == requested:
            suffixed.add(ip)
    return next(iter(suffixed)) if len(suffixed) == 1 else None


class ReconnectBackoff:
    """Bounded, device-scoped retry delays that reset on success."""

    def __init__(self, base_seconds: float = 30, max_seconds: float = 900):
        self.base_seconds = base_seconds
        self.max_seconds = max_seconds
        self._failures: dict[str, int] = {}
        self._retry_at: dict[str, float] = {}

    def remaining(self, key: str, now: float | None = None) -> float:
        clock = time.monotonic() if now is None else now
        return max(0.0, self._retry_at.get(key, 0.0) - clock)

    def can_retry(self, key: str, now: float | None = None) -> bool:
        return self.remaining(key, now) <= 0

    def record_failure(self, key: str, now: float | None = None) -> float:
        clock = time.monotonic() if now is None else now
        failures = min(self._failures.get(key, 0) + 1, 32)
        self._failures[key] = failures
        delay = min(self.max_seconds, self.base_seconds * (2 ** (failures - 1)))
        self._retry_at[key] = clock + delay
        return delay

    def failures(self, key: str) -> int:
        return self._failures.get(key, 0)

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)
        self._retry_at.pop(key, None)

    def clear(self) -> None:
        self._failures.clear()
        self._retry_at.clear()


async def terminate_process(
    process, terminate_timeout: float = 5.0, kill_timeout: float = 2.0
) -> None:
    """Terminate and always reap a subprocess after timeout or cancellation."""
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=terminate_timeout)
        return
    except asyncio.TimeoutError:
        pass
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.wait(), timeout=kill_timeout)
    except asyncio.TimeoutError:
        # A process in uninterruptible kernel sleep cannot be reaped here.
        pass
