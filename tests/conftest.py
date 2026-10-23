"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Generator

import pytest
import pytest_socket


@pytest.fixture(autouse=True)
def _allow_localhost(socket_enabled: None) -> Generator[None]:
    """The fake TTP server needs real loopback sockets; nothing else is allowed."""
    pytest_socket.socket_allow_hosts(["127.0.0.1"], allow_unix_socket=True)
    yield


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA load custom_components/ from this repo."""
