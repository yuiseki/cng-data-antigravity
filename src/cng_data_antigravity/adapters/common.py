from __future__ import annotations

from datetime import datetime, timezone
from urllib.request import Request, urlopen

_USER_AGENT = "cng-data-antigravity/0.1 (+https://github.com/yuiseki/cng-data-antigravity)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_request(url: str, *, method: str = "GET", extra_headers: dict[str, str] | None = None) -> Request:
    headers = {"User-Agent": _USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    return Request(url, method=method, headers=headers)


def head(url: str) -> dict[str, str]:
    request = make_request(url, method="HEAD")
    with urlopen(request, timeout=30) as response:
        return {k.lower(): v for k, v in response.headers.items()}
