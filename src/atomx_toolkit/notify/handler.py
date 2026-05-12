"""logging.Handler that dispatches toolkit_error emails on WARNING+ records."""

from __future__ import annotations

import logging
from collections.abc import Callable

from atomx_toolkit.notify.dedup import DedupState, should_send_toolkit_error

ToolkitErrorSender = Callable[..., None]
"""Signature: sender(*, subject: str, body: str) -> None."""


class ToolkitErrorHandler(logging.Handler):
    def __init__(
        self,
        sender: ToolkitErrorSender,
        dedup: DedupState,
        level: int = logging.WARNING,
    ) -> None:
        super().__init__(level=level)
        self._sender = sender
        self._dedup = dedup

    def emit(self, record: logging.LogRecord) -> None:
        try:
            body = self.format(record)
            if not should_send_toolkit_error(self._dedup, body):
                return
            self._sender(subject="[atomx-toolkit] toolkit error", body=body)
        except Exception:  # never let logging crash the app
            self.handleError(record)
