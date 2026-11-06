"""Safe URL preparation for the opt-in Cast custom-card recovery module.

The casting URL gets one small query flag so the already-loaded Home Assistant
frontend knows this is a CCD-controlled dashboard. Dashboard configuration,
selection and readiness matching retain the original URL.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

RECOVERY_QUERY_KEY = "ccd_cast_guard"


def prepare_cast_url(dashboard_url: str, enabled: bool = False) -> str:
    """Apply the explicit Cast-only recovery flag, preserving other URL parts.

    Normal dashboards must not be modified. Refuse non-HTTP URLs rather than
    introducing recovery on arbitrary URI schemes.
    """
    if not enabled:
        return dashboard_url

    parts = urlsplit(dashboard_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return dashboard_url

    pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != RECOVERY_QUERY_KEY
    ]
    pairs.append((RECOVERY_QUERY_KEY, "1"))

    return urlunsplit(parts._replace(query=urlencode(pairs)))
