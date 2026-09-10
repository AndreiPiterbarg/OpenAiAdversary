"""Minimal JSON-over-HTTP helper so served and vendor backends need no extra dependency."""

import json
import urllib.error
import urllib.request
from typing import Any


class HttpError(RuntimeError):
    """A non-2xx response or transport failure."""


def post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    """POST ``payload`` as JSON and decode the JSON response.

    Raises:
        HttpError: On transport errors or non-2xx status, with the response body attached.
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed scheme by caller
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HttpError(f"{exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"transport error for {url}: {exc.reason}") from exc
