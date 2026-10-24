"""Tests for the TTP client against the fake server."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from custom_components.tesira.client import (
    IacFilter,
    TesiraAuthError,
    TesiraClient,
    TesiraCommandError,
    TesiraConnectionError,
    TesiraTimeoutError,
    parse_value,
    strip_control,
)

from .fake_tesira import FakeTesira


@pytest.fixture
async def server() -> AsyncIterator[FakeTesira]:
    fake = FakeTesira()
    fake.add("SourceRouterKlubRaum", "sourceSelection", 4)
    fake.add("LevelSaal", "level", -32.8, 1)
    fake.add("LevelSaal", "mute", False, 1)
    await fake.start()
    yield fake
    await fake.stop()


def make_client(server: FakeTesira, **kwargs: Any) -> TesiraClient:
    return TesiraClient(
        "127.0.0.1",
        server.port,
        backoff_start=0.02,
        backoff_max=0.1,
        command_timeout=0.3,
        **kwargs,
    )


async def wait_until(predicate: Any, timeout: float = 3.0) -> None:  # noqa: ASYNC109
    async with asyncio.timeout(timeout):
        while not predicate():  # noqa: ASYNC110
            await asyncio.sleep(0.01)


@pytest.fixture
async def client(server: FakeTesira) -> AsyncIterator[TesiraClient]:
    c = make_client(server)
    c.start()
    await wait_until(lambda: c.connected)
    yield c
    await c.stop()


def test_parse_value() -> None:
    assert parse_value("true") is True
    assert parse_value("4") == 4
    assert parse_value("-32.8") == -32.8
    assert parse_value('"abc"') == "abc"
    assert parse_value("[1 2]") == "[1 2]"


def test_iac_filter_strips_and_refuses() -> None:
    f = IacFilter()
    out = f.feed(
        bytes([0xFF, 0xFD, 1, 0x41, 0xFF, 0xFB, 3, 0xFF, 0xFA, 31, 0, 80, 0xFF, 0xF0, 0x42])
    )
    assert out == b"AB"
    assert bytes(f.replies) == bytes([0xFF, 0xFC, 1, 0xFF, 0xFE, 3])


async def test_get_and_set_with_push(server: FakeTesira) -> None:
    pushes: list[tuple[str, Any]] = []
    c = make_client(server)
    c.set_callbacks(on_push=lambda label, value: pushes.append((label, value)))
    c.start()
    await wait_until(lambda: c.connected)
    try:
        assert await c.get("SourceRouterKlubRaum", "sourceSelection") == 4
        await c.subscribe("SourceRouterKlubRaum", "sourceSelection", "src")
        await c.set("SourceRouterKlubRaum", "sourceSelection", 2)
        await wait_until(lambda: ("src", 2) in pushes)
        assert server.values[("SourceRouterKlubRaum", "sourceSelection", None)] == 2
    finally:
        await c.stop()


async def test_level_and_mute(client: TesiraClient, server: FakeTesira) -> None:
    assert await client.get("LevelSaal", "level", 1) == -32.8
    await client.set("LevelSaal", "level", -20.0, 1)
    await client.set("LevelSaal", "mute", True, 1)
    assert '"LevelSaal" set level 1 -20.0' in server.received
    assert '"LevelSaal" set mute 1 true' in server.received
    assert await client.get("LevelSaal", "mute", 1) is True


async def test_err_raises_and_keeps_pairing(client: TesiraClient) -> None:
    with pytest.raises(TesiraCommandError):
        await client.get("Missing", "level", 1)
    # The next command must still get its own answer.
    assert await client.get("LevelSaal", "level", 1) == -32.8


async def test_push_between_command_and_reply_is_not_a_reply(
    server: FakeTesira,
) -> None:
    c = make_client(server)
    c.start()
    await wait_until(lambda: c.connected)
    try:
        await c.subscribe("LevelSaal", "level", "lvl", 1)
        await server.set_external("LevelSaal", "level", -10.0, 1)
        assert await c.get("LevelSaal", "level", 1) == -10.0
    finally:
        await c.stop()


async def test_timeout_drops_connection_and_reconnects(
    client: TesiraClient, server: FakeTesira
) -> None:
    server.swallow_next = 1
    with pytest.raises(TesiraTimeoutError):
        await client.get("LevelSaal", "level", 1)
    await wait_until(lambda: not client.connected)
    await wait_until(lambda: client.connected)
    assert await client.get("LevelSaal", "level", 1) == -32.8


async def test_reconnect_runs_on_connect_hook_again(server: FakeTesira) -> None:
    calls = 0
    states: list[bool] = []
    c = make_client(server)

    async def hook() -> None:
        nonlocal calls
        calls += 1
        await c.subscribe("LevelSaal", "level", "lvl", 1)

    c.set_callbacks(on_connect=hook, on_state=states.append)
    c.start()
    try:
        await wait_until(lambda: c.connected)
        await server.drop_connections()
        await wait_until(lambda: calls == 2 and c.connected)
        assert states == [True, False, True]
    finally:
        await c.stop()


async def test_commands_after_stop_raise(server: FakeTesira) -> None:
    c = make_client(server)
    c.start()
    await wait_until(lambda: c.connected)
    await c.stop()
    assert not c.connected
    with pytest.raises(TesiraConnectionError):
        await c.get("LevelSaal", "level", 1)


async def test_backoff_until_server_returns() -> None:
    fake = FakeTesira()
    fake.add("LevelSaal", "level", -1.0, 1)
    await fake.start()
    port = fake.port
    await fake.stop()
    c = TesiraClient("127.0.0.1", port, backoff_start=0.02, backoff_max=0.05)
    c.start()
    try:
        await asyncio.sleep(0.15)
        assert not c.connected
        await fake.start(port)
        await wait_until(lambda: c.connected)
    finally:
        await c.stop()
        await fake.stop()


async def test_stop_leaves_no_tasks(server: FakeTesira) -> None:
    before = asyncio.all_tasks()
    c = make_client(server)
    c.start()
    await wait_until(lambda: c.connected)
    await c.stop()
    await wait_until(lambda: server.connection_count == 0)
    await asyncio.sleep(0)
    assert asyncio.all_tasks() == before


async def test_login() -> None:
    fake = FakeTesira(username="admin", password="secret")
    fake.add("LevelSaal", "level", -1.0, 1)
    await fake.start()
    try:
        ok = TesiraClient("127.0.0.1", fake.port, username="admin", password="secret")
        await ok.probe()
        bad = TesiraClient("127.0.0.1", fake.port, username="admin", password="nope")
        with pytest.raises(TesiraAuthError):
            await bad.probe()
    finally:
        await fake.stop()


async def test_protocol_log_is_limited_and_hides_credentials() -> None:
    fake = FakeTesira(username="admin", password="secret")
    fake.add("LevelSaal", "level", -1.0, 1)
    await fake.start()
    c = TesiraClient("127.0.0.1", fake.port, username="admin", password="secret")
    c.start()
    try:
        await wait_until(lambda: c.connected)
        for _ in range(60):
            await c.get("LevelSaal", "level", 1)
        assert len(c.protocol_log) == 50
        assert not any("secret" in line for line in c.protocol_log)
    finally:
        await c.stop()
        await fake.stop()


async def test_invalid_identifiers_rejected(client: TesiraClient) -> None:
    with pytest.raises(ValueError):
        await client.get('Bad"Tag', "level", 1)
    with pytest.raises(ValueError):
        await client.get("Tag", "level; drop", 1)


def test_strip_control_keeps_text_and_newlines() -> None:
    assert (
        strip_control(b"SourceRouterSaal.s\x08ourceSelection\r\n")
        == b"SourceRouterSaal.sourceSelection\n"
    )
    assert strip_control(b"a\x00b\x07c\x1bd\x7fe\tf") == b"abcdef"
    assert strip_control("Außen".encode()) == "Außen".encode()


async def test_control_characters_in_echo_and_push_are_ignored(
    server: FakeTesira,
) -> None:
    server.control_chars = True
    pushes: list[tuple[str, Any]] = []
    c = make_client(server)
    c.set_callbacks(on_push=lambda label, value: pushes.append((label, value)))
    c.start()
    await wait_until(lambda: c.connected)
    try:
        assert await c.get("SourceRouterKlubRaum", "sourceSelection") == 4
        await c.subscribe(
            "SourceRouterKlubRaum", "sourceSelection", "SourceRouterKlubRaum.sourceSelection"
        )
        await server.set_external("SourceRouterKlubRaum", "sourceSelection", 2)
        await wait_until(lambda: ("SourceRouterKlubRaum.sourceSelection", 2) in pushes)
        for line in c.protocol_log:
            assert all(ch == "\n" or (ch >= " " and ch != "\x7f") for ch in line), repr(line)
    finally:
        await c.stop()
