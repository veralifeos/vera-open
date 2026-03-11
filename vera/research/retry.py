"""Shared retry configuration for research HTTP calls."""

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=2, min=2, max=8),
    "retry": retry_if_exception_type((httpx.HTTPError, TimeoutError)),
    "reraise": True,
}

retry_httpx = retry(**RETRY_KWARGS)
"""Decorator for httpx calls with 3 attempts and exponential backoff."""
