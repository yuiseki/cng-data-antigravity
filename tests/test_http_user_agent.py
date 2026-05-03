"""Tests for User-Agent header on all outbound HTTP requests.

Regression: mapterhorn.com (and other CDNs) return 403 Forbidden when
Python's default "Python-urllib/3.x" User-Agent is used.  All HTTP
requests must go through make_request() which sets a descriptive UA.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from cng_data_antigravity.adapters import common as common_mod
from cng_data_antigravity.adapters import pmtiles as pmtiles_adapter
from cng_data_antigravity.adapters.common import _USER_AGENT, make_request


def test_make_request_sets_user_agent():
    req = make_request("https://example.com/data.pmtiles")
    # urllib Request stores headers with title-case key
    assert req.get_header("User-agent") == _USER_AGENT


def test_make_request_preserves_extra_headers():
    req = make_request("https://example.com/data.pmtiles", extra_headers={"Range": "bytes=0-127"})
    assert req.get_header("User-agent") == _USER_AGENT
    assert req.get_header("Range") == "bytes=0-127"


def test_head_sends_user_agent(monkeypatch):
    """head() must include the User-Agent so servers like mapterhorn.com don't return 403."""
    captured: dict = {}

    fake_response = MagicMock()
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = MagicMock(return_value=False)
    fake_response.headers.items.return_value = [("content-length", "12345")]

    def fake_urlopen(req, timeout=None):
        captured["user_agent"] = req.get_header("User-agent")
        captured["method"] = req.get_method()
        return fake_response

    monkeypatch.setattr(common_mod, "urlopen", fake_urlopen)
    common_mod.head("https://download.mapterhorn.com/planet.pmtiles")

    assert captured["user_agent"] == _USER_AGENT
    assert captured["method"] == "HEAD"


def test_pmtiles_range_request_sends_user_agent(monkeypatch):
    """HTTP range requests for PMTiles bbox extraction must include User-Agent.

    Regression: mapterhorn.com returns 403 without a proper User-Agent.
    """
    captured: dict = {}

    fake_response = MagicMock()
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = MagicMock(return_value=False)
    fake_response.read.return_value = b"\x00" * 16

    def fake_urlopen(req, timeout=None):
        captured["user_agent"] = req.get_header("User-agent")
        captured["range"] = req.get_header("Range")
        return fake_response

    monkeypatch.setattr(pmtiles_adapter, "urlopen", fake_urlopen)

    fetch = pmtiles_adapter._http_range_source("https://download.mapterhorn.com/planet.pmtiles")
    fetch(0, 16)

    assert captured["user_agent"] == _USER_AGENT
    assert captured["range"] == "bytes=0-15"
