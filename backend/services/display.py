"""Wi-Fi bridge for sending relay status to an ESP32 display controller."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen


logger = logging.getLogger(__name__)


class EspDisplayService:
    def __init__(self) -> None:
        self.enabled = True
        self.base_url = os.getenv("ESP_DISPLAY_URL", "http://192.168.4.1")
        self.request_timeout_s = float(os.getenv("ESP_DISPLAY_TIMEOUT", "0.5"))
        self._last_query = ""
        self._last_send_at = 0.0
        self._last_error = ""
        self._last_error_at = 0.0

    def _build_params(self, relay_status) -> Dict[str, str]:
        phases = ",".join(relay_status.last_trip_phases) if relay_status.last_trip_phases else "-"
        idiff = ",".join(f"{value:.2f}" for value in relay_status.i_diff_amp)
        thresholds = ",".join(f"{value:.2f}" for value in relay_status.threshold_amp)
        return {
            "state": relay_status.status,
            "family": relay_status.vector_family or "UNKNOWN",
            "tap": str(relay_status.tap_position),
            "phases": phases,
            "idiff": idiff,
            "threshold": thresholds,
            "count": str(relay_status.trip_count),
        }

    def _send_status(self, params: Dict[str, str]) -> None:
        query = urlencode(params)
        url = f"{self.base_url.rstrip('/')}/status?{query}"
        with urlopen(url, timeout=self.request_timeout_s) as response:
            response.read()
        self._last_query = query
        self._last_send_at = time.time()
        self._last_error = ""

    async def push_relay_status(self, relay_status) -> None:
        if not self.enabled:
            return

        params = self._build_params(relay_status)
        query = urlencode(params)
        now = time.time()
        if query == self._last_query and (now - self._last_send_at) < 0.5:
            return

        try:
            await asyncio.to_thread(self._send_status, params)
        except (TimeoutError, URLError, OSError) as exc:
            message = str(exc)
            if message != self._last_error or (now - self._last_error_at) > 5.0:
                logger.warning("ESP display Wi-Fi send failed: %s", exc)
                self._last_error = message
                self._last_error_at = now

    async def show_test_message(self, message: str = "HELLO") -> bool:
        if not self.enabled:
            return False

        query = urlencode({"message": message})
        url = f"{self.base_url.rstrip('/')}/hello?{query}"

        def _send() -> None:
            with urlopen(url, timeout=self.request_timeout_s) as response:
                response.read()

        try:
            await asyncio.to_thread(_send)
            return True
        except (TimeoutError, URLError, OSError) as exc:
            logger.warning("ESP display HELLO test failed: %s", exc)
            return False

    async def shutdown(self) -> None:
        return


esp_display_service = EspDisplayService()
