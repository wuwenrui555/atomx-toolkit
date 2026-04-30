"""Mock SMTP server fixture using aiosmtpd."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from aiosmtpd.controller import Controller


@dataclass
class _CapturedEmail:
    sender: str
    recipients: list[str]
    raw: bytes


class _Sink:
    def __init__(self) -> None:
        self.messages: list[_CapturedEmail] = []

    async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:
        self.messages.append(
            _CapturedEmail(
                sender=envelope.mail_from,
                recipients=list(envelope.rcpt_tos),
                raw=envelope.content,
            )
        )
        return "250 OK"


@dataclass
class FakeSmtp:
    host: str
    port: int
    sink: _Sink


def _find_free_port() -> int:
    """Pick an unused TCP port. aiosmtpd Controller cannot use port=0 because
    its post-start trigger reads self.port verbatim (not the actually-bound port).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def fake_smtp() -> Iterator[FakeSmtp]:
    sink = _Sink()
    port = _find_free_port()
    controller = Controller(sink, hostname="127.0.0.1", port=port)
    controller.start()
    try:
        yield FakeSmtp(host=controller.hostname, port=port, sink=sink)
    finally:
        controller.stop()
