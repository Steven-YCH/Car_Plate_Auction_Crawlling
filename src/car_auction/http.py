"""Shared HTTP helpers with polite defaults for TD requests."""

from __future__ import annotations

import time
from typing import Optional

import requests

from .config import download as dl_cfg

_SESSION: Optional[requests.Session] = None
_LAST_REQUEST_AT = 0.0


def get_session() -> requests.Session:
    """Return a process-wide Session with a descriptive User-Agent."""

    global _SESSION
    if _SESSION is None:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": dl_cfg.user_agent,
                "Accept": "*/*",
            }
        )
        _SESSION = session
    return _SESSION


def _throttle() -> None:
    global _LAST_REQUEST_AT
    delay = max(0.0, float(dl_cfg.request_delay_seconds))
    if delay <= 0:
        return
    now = time.monotonic()
    wait_for = delay - (now - _LAST_REQUEST_AT)
    if wait_for > 0:
        time.sleep(wait_for)
    _LAST_REQUEST_AT = time.monotonic()


def request(
    method: str,
    url: str,
    *,
    timeout: Optional[float] = None,
    stream: bool = False,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> requests.Response:
    """Issue an HTTP request with throttle + retry."""

    sess = session or get_session()
    timeout = dl_cfg.timeout_seconds if timeout is None else timeout
    last_error: Exception | None = None

    for attempt in range(1, dl_cfg.max_retries + 1):
        try:
            _throttle()
            resp = sess.request(method, url, timeout=timeout, stream=stream, **kwargs)
            if resp.status_code in {429, 500, 502, 503, 504} and attempt < dl_cfg.max_retries:
                time.sleep(min(8.0, 0.75 * attempt))
                continue
            return resp
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= dl_cfg.max_retries:
                raise
            time.sleep(min(8.0, 0.75 * attempt))

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request failed without response: {method} {url}")


def get(url: str, **kwargs) -> requests.Response:
    return request("GET", url, **kwargs)


def head(url: str, **kwargs) -> requests.Response:
    return request("HEAD", url, **kwargs)
