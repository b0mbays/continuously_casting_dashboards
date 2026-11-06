"""Safe URL preparation for the opt-in Cast custom-card recovery module.

The casting URL gets one small query flag so the already-loaded Home Assistant
frontend knows this is a CCD-controlled dashboard. Dashboard configuration,
selection and readiness matching retain the original URL.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

RECOVERY_QUERY_KEY = "ccd_cast_guard"


def prepare_cast_url(
    dashboard_url: str, enabled: bool = False, diagnostic_target: str | None = None
) -> str:
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
        if key not in (RECOVERY_QUERY_KEY, "ccd_cast_target")
    ]
    pairs.append((RECOVERY_QUERY_KEY, "1"))
    if diagnostic_target is not None:
        if len(diagnostic_target) != 16 or any(
            ch not in "0123456789abcdef" for ch in diagnostic_target
        ):
            raise ValueError("Invalid Cast diagnostic correlation token")
        pairs.append(("ccd_cast_target", diagnostic_target))

    return urlunsplit(parts._replace(query=urlencode(pairs)))
