"""Fake Tesira TTP server for tests (asyncio, no HA imports)."""

from __future__ import annotations

import asyncio
import re
from typing import Any

IAC, DO, WILL = 0xFF, 0xFD, 0xFB

_CMD_RE = re.compile(
    r'^"(?P<tag>[^"]+)"\s+(?P<verb>get|set|subscribe|unsubscribe)\s+(?P<attr>\w+)'
    r"(?P<rest>.*)$"
)
_INDEX_ATTRS = {"level", "mute", "inputLabel"}

Key = tuple[str, str, int | None]


_IAC_SEQ = re.compile(rb"\xff[\xfb-\xfe].")


def clean(data: bytes) -> str:
    """Decode a received line without Telnet negotiation bytes."""
    return _IAC_SEQ.sub(b"", data).decode(errors="replace").strip()


def fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


class FakeTesira:
    """Minimal TTP server: IAC offer, banner, echo, +OK/-ERR, subscriptions."""

    def __init__(self, *, username: str | None = None, password: str | None = None) -> None:
        self.values: dict[Key, Any] = {}
        self.received: list[str] = []
        self.port = 0
        self.username = username
        self.password = password
        self.swallow_next = 0  # number of commands to ignore (timeout tests)
        # Values that change right before a subscribe is handled, i.e. after
        # the client has already read them with get.
        self.change_before_subscribe: dict[Key, Any] = {}
        self.reject_login = False
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        # (writer, key) -> label
        self._subs: dict[tuple[asyncio.StreamWriter, Key], str] = {}

    # -- setup helpers -------------------------------------------------

    def add(self, tag: str, attr: str, value: Any, index: int | None = None) -> None:
        self.values[(tag, attr, index)] = value

    @property
    def connection_count(self) -> int:
        return len(self._writers)

    async def start(self, port: int = 0) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop listening and drop every connection."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
        await self.drop_connections()
        if server is not None:
            await server.wait_closed()

    async def drop_connections(self) -> None:
        for writer in list(self._writers):
            writer.transport.abort()
        self._writers.clear()
        self._subs.clear()
        await asyncio.sleep(0)

    # -- external changes ----------------------------------------------

    async def set_external(self, tag: str, attr: str, value: Any, index: int | None = None) -> None:
        """Change a value as if done in the Tesira software, and push it."""
        key = (tag, attr, index)
        self.values[key] = value
        await self._publish(key)

    async def _publish(self, key: Key) -> None:
        for (writer, sub_key), label in list(self._subs.items()):
            if sub_key == key and not writer.is_closing():
                value = fmt(self.values[key])
                writer.write(f'! "publishToken":"{label}" "value":{value}\r\n'.encode())
                await writer.drain()

    # -- connection handling -------------------------------------------

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._server is None:
            # Accepted just while stopping: refuse, or wait_closed() would hang.
            writer.transport.abort()
            return
        self._writers.add(writer)
        try:
            writer.write(bytes([IAC, DO, 1, IAC, WILL, 3, IAC, DO, 31]))
            if self.username is not None:
                if not await self._login(reader, writer):
                    return
            writer.write(b"\r\nWelcome to the Tesira Text Protocol Server...\r\n\r\n")
            await writer.drain()
            while True:
                data = await reader.readline()
                if not data:
                    break
                line = clean(data)
                if not line:
                    continue
                await self._command(writer, line)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self._writers.discard(writer)
            for key in [k for k in self._subs if k[0] is writer]:
                del self._subs[key]
            writer.close()

    async def _login(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        writer.write(b"login: ")
        await writer.drain()
        user = clean(await reader.readline())
        writer.write(b"password: ")
        await writer.drain()
        pwd = clean(await reader.readline())
        if self.reject_login or user != self.username or pwd != self.password:
            writer.write(b"login: ")
            await writer.drain()
            await asyncio.sleep(0.05)
            return False
        return True

    async def _command(self, writer: asyncio.StreamWriter, line: str) -> None:
        self.received.append(line)
        if self.swallow_next > 0:
            self.swallow_next -= 1
            return
        writer.write(line.encode() + b"\r\n")  # echo
        if line.startswith("SESSION set verbose"):
            writer.write(b"+OK\r\n")
            await writer.drain()
            return
        match = _CMD_RE.match(line)
        if match is None:
            writer.write(b"-ERR GENERAL_FAILURE: unparsed\r\n")
            await writer.drain()
            return
        tag, verb, attr = match["tag"], match["verb"], match["attr"]
        rest = match["rest"].strip()
        index: int | None = None
        if attr in _INDEX_ATTRS and rest:
            first, _, rest = rest.partition(" ")
            index = int(first)
            rest = rest.strip()
        key: Key = (tag, attr, index)
        if not any(k[0] == tag for k in self.values):
            writer.write(
                b'-ERR address not found: {"deviceId":0 "classCode":0 "instanceNum":0}\r\n'
            )
        elif verb == "get":
            if key in self.values:
                writer.write(f'+OK "value":{fmt(self.values[key])}\r\n'.encode())
            else:
                writer.write(b"-ERR INVALID_PARAMETER\r\n")
        elif verb == "set":
            if key not in self.values:
                writer.write(b"-ERR INVALID_PARAMETER\r\n")
            else:
                old = self.values[key]
                if isinstance(old, bool):
                    self.values[key] = rest.lower() == "true"
                elif isinstance(old, int):
                    self.values[key] = int(rest)
                else:
                    self.values[key] = float(rest)
                writer.write(b"+OK\r\n")
                await writer.drain()
                await self._publish(key)
                return
        elif verb == "subscribe":
            if key in self.change_before_subscribe:
                self.values[key] = self.change_before_subscribe.pop(key)
            label = rest.strip('"')
            self._subs[(writer, key)] = label
            writer.write(b"+OK\r\n")
            await writer.drain()
            await self._publish(key)  # initial publish like the real device
            return
        else:  # unsubscribe
            self._subs.pop((writer, key), None)
            writer.write(b"+OK\r\n")
        await writer.drain()
