from __future__ import annotations

from datetime import datetime, timezone
from urllib.request import Request, urlopen


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def head(url: str) -> dict[str, str]:
    request = Request(url, method="HEAD")
    with urlopen(request, timeout=30) as response:
        return {k.lower(): v for k, v in response.headers.items()}
