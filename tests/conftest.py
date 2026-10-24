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


# ---------------------------------------------------------------------------
# Integration fixtures
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from typing import Any  # noqa: E402

from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.tesira import const  # noqa: E402
from custom_components.tesira.const import DOMAIN  # noqa: E402
from custom_components.tesira.coordinator import TesiraCoordinator  # noqa: E402

from .fake_tesira import FakeTesira  # noqa: E402


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("custom_components.tesira.coordinator.BACKOFF_START", 0.02)
    monkeypatch.setattr("custom_components.tesira.coordinator.BACKOFF_MAX", 0.1)


@pytest.fixture
async def fake() -> AsyncIterator[FakeTesira]:
    """A Tesira with all default blocks, every router on source 3 (Musik)."""
    server = FakeTesira()
    for _name, router, level, gate, ducker in const.DEFAULT_ZONES.values():
        if router:
            server.add(router, "sourceSelection", 3)
        server.add(level, "level", -32.8, 1)
        server.add(level, "mute", False, 1)
        if gate:
            server.add(gate, "mute", True, 1)  # microphones blocked
        if ducker:
            server.add(ducker, "bypass", False)
            server.add(ducker, "duckingLevel", -20.0)
    await server.start()
    yield server
    await server.stop()


def make_entry(
    fake: FakeTesira, options: dict[str, Any] | None = None, **kwargs: Any
) -> MockConfigEntry:
    kwargs.setdefault("version", 3)
    kwargs.setdefault("unique_id", "127.0.0.1")
    return MockConfigEntry(
        domain=DOMAIN,
        title="Tesira",
        data={"host": "127.0.0.1", "port": fake.port, "name": "Tesira"},
        options=options or {},
        **kwargs,
    )


async def wait_for(predicate: Any, timeout: float = 3.0) -> None:  # noqa: ASYNC109
    async with asyncio.timeout(timeout):
        while not predicate():  # noqa: ASYNC110
            await asyncio.sleep(0.01)


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> TesiraCoordinator:
    """Set the entry up and wait until the Tesira connection is synchronised."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await wait_for(lambda: entry.runtime_data.connected)
    await hass.async_block_till_done()
    coordinator: TesiraCoordinator = entry.runtime_data
    return coordinator
