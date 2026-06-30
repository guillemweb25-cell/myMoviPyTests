from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from decouple import config


@dataclass
class ComfyUiStatus:
    configured: bool
    online: bool
    url: str | None
    pending: int | None = None
    running: int | None = None
    error: str | None = None


class ComfyUiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 4.0) -> None:
        self.base_url = (base_url or config("COMFY_URL", default="")).strip().rstrip("/")
        self.timeout = timeout

    def status(self) -> ComfyUiStatus:
        if not self.base_url:
            return ComfyUiStatus(configured=False, online=False, url=None)

        try:
            self._get_json("/system_stats")
            queue = self._get_json("/queue")
            pending, running = self._parse_queue(queue)
            return ComfyUiStatus(
                configured=True,
                online=True,
                url=self.base_url,
                pending=pending,
                running=running,
            )
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return ComfyUiStatus(
                configured=True,
                online=False,
                url=self.base_url,
                error=str(exc),
            )

    def _get_json(self, path: str) -> dict[str, Any]:
        request = Request(urljoin(f"{self.base_url}/", path.lstrip("/")))
        with urlopen(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise json.JSONDecodeError("Expected JSON object", raw, 0)
        return payload

    @staticmethod
    def _parse_queue(queue: dict[str, Any]) -> tuple[int, int]:
        pending_items = queue.get("queue_pending", [])
        running_items = queue.get("queue_running", [])
        pending = len(pending_items) if isinstance(pending_items, list) else 0
        running = len(running_items) if isinstance(running_items, list) else 0
        return pending, running
