"""Async client for the Biamp Tesira Text Protocol (TTP) over Telnet.

This module has no Home Assistant imports and can be tested on its own.

Design notes:
* One TCP connection, commands are strictly serial (one request in flight).
* Echo lines and anything else that is not ``+OK`` / ``-ERR`` / ``!`` are
  ignored, so a bad line cannot shift the request/response pairing.
* Push lines (``! "publishToken":"<label>" "value":<v>``) are routed to a
  callback and never touch the pending request.
* After a command timeout the connection is dropped and re-established, since
  a late answer could otherwise be paired with the next command.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

BANNER = "welcome to the tesira"
COMMAND_TIMEOUT = 5.0
CONNECT_TIMEOUT = 10.0
HANDSHAKE_TIMEOUT = 10.0
BACKOFF_START = 1.0
BACKOFF_MAX = 30.0
LOG_LINES = 50

_OK_RE = re.compile(r'^\+OK(?:\s+"?value"?\s*:\s*(.*))?$')
_PUSH_RE = re.compile(r'^!\s+"publishToken"\s*:\s*"([^"]*)"\s+"value"\s*:\s*(.*)$')

# Telnet command bytes
IAC = 0xFF
DONT = 0xFE
DO = 0xFD
WONT = 0xFC
WILL = 0xFB
SB = 0xFA
SE = 0xF0


class TesiraError(Exception):
    """Base class for client errors."""


class TesiraConnectionError(TesiraError, ConnectionError):
    """The connection is down or was lost."""


class TesiraTimeoutError(TesiraConnectionError):
    """A command or the handshake timed out."""


class TesiraCommandError(TesiraError):
    """The device answered ``-ERR``."""


class TesiraAuthError(TesiraConnectionError):
    """Login was requested but could not be completed."""


class IacFilter:
    """Strip Telnet IAC sequences from a byte stream.

    Cleaned payload bytes are returned by ``feed``; replies refusing every
    offered option are collected in ``replies`` for the caller to send.
    """

    def __init__(self) -> None:
        self.replies = bytearray()
        self._state = "data"
        self._command = 0

    def feed(self, data: bytes) -> bytes:
        out = bytearray()
        for byte in data:
            if self._state == "data":
                if byte == IAC:
                    self._state = "iac"
                else:
                    out.append(byte)
            elif self._state == "iac":
                if byte == IAC:
                    out.append(IAC)
                    self._state = "data"
                elif byte in (DO, DONT, WILL, WONT):
                    self._command = byte
                    self._state = "option"
                elif byte == SB:
                    self._state = "subneg"
                else:
                    self._state = "data"
            elif self._state == "option":
                if self._command == DO:
                    self.replies.extend((IAC, WONT, byte))
                elif self._command == WILL:
                    self.replies.extend((IAC, DONT, byte))
                self._state = "data"
            elif self._state == "subneg":
                if byte == IAC:
                    self._state = "subneg_iac"
            elif self._state == "subneg_iac":
                self._state = "data" if byte == SE else "subneg"
        return bytes(out)


# Everything below 0x20 except the line feed, plus DEL. Echo lines can contain
# stray control characters (e.g. a backspace inside a tag), which would break
# matching of tags and labels.
_CONTROL_BYTES = bytes(b for b in range(0x20) if b != 0x0A) + b"\x7f"


def strip_control(data: bytes) -> bytes:
    """Remove control characters (but keep ``\\n`` as the line separator)."""
    return data.translate(None, _CONTROL_BYTES)


def parse_value(raw: str) -> Any:
    """Convert a TTP value string to bool, int, float or str.

    Anything structured (lists, maps) is returned as the raw string.
    """
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def format_value(value: Any) -> str:
    """Format a Python value for a ``set`` command."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.1f}" if value == round(value, 1) else f"{value:.3f}"
    return str(value)


def _quote(text: str) -> str:
    """Quote an instance tag or label; refuse anything that could break out."""
    if not text or any(ch in text for ch in '"\r\n\\'):
        raise ValueError(f"Invalid TTP identifier: {text!r}")
    return f'"{text}"'


class TesiraClient:
    """Persistent TTP client with automatic reconnect."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        username: str | None = None,
        password: str | None = None,
        verbose_off: bool = False,
        backoff_start: float = BACKOFF_START,
        backoff_max: float = BACKOFF_MAX,
        command_timeout: float = COMMAND_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._verbose_off = verbose_off
        self._backoff_start = backoff_start
        self._backoff_max = backoff_max
        self._command_timeout = command_timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._iac = IacFilter()
        self._buffer = bytearray()

        self._lock = asyncio.Lock()
        self._pending: asyncio.Future[Any] | None = None
        self._link_up = False
        self._connected = False

        self._task: asyncio.Task[None] | None = None
        self._read_task: asyncio.Task[None] | None = None

        self._on_push: Callable[[str, Any], None] | None = None
        self._on_connect: Callable[[], Awaitable[None]] | None = None
        self._on_state: Callable[[bool], None] | None = None

        self.protocol_log: deque[str] = deque(maxlen=LOG_LINES)
        self.last_error: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        """True once the handshake and the on_connect hook have completed."""
        return self._connected

    def set_callbacks(
        self,
        *,
        on_push: Callable[[str, Any], None] | None = None,
        on_connect: Callable[[], Awaitable[None]] | None = None,
        on_state: Callable[[bool], None] | None = None,
    ) -> None:
        """Register callbacks.

        ``on_connect`` runs on every (re)connect with commands enabled; the
        client counts as connected after it returns. ``on_state`` is called
        with True/False when that status changes.
        """
        self._on_push = on_push
        self._on_connect = on_connect
        self._on_state = on_state

    def start(self) -> None:
        """Start the connection loop in the background."""
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        """Stop the loop and close the connection."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def probe(self) -> None:
        """Connect, finish the handshake and close again (for config flows)."""
        try:
            await self._open()
        finally:
            await self._close()

    async def get(self, tag: str, attribute: str, index: int | None = None) -> Any:
        """Read an attribute and return its parsed value."""
        return await self._command(self._build(tag, "get", attribute, index))

    async def set(self, tag: str, attribute: str, value: Any, index: int | None = None) -> None:
        """Write an attribute."""
        await self._command(self._build(tag, "set", attribute, index, value))

    async def subscribe(
        self, tag: str, attribute: str, label: str, index: int | None = None
    ) -> None:
        """Subscribe to changes; pushes arrive via on_push as ``(label, value)``."""
        await self._command(self._build(tag, "subscribe", attribute, index, extra=_quote(label)))

    # ------------------------------------------------------------------
    # Command handling
    # ------------------------------------------------------------------

    @staticmethod
    def _build(
        tag: str,
        verb: str,
        attribute: str,
        index: int | None,
        value: Any = None,
        extra: str | None = None,
    ) -> str:
        if not re.fullmatch(r"[A-Za-z0-9]+", attribute):
            raise ValueError(f"Invalid TTP attribute: {attribute!r}")
        parts = [_quote(tag), verb, attribute]
        if index is not None:
            parts.append(str(int(index)))
        if value is not None:
            text = format_value(value)
            if "\r" in text or "\n" in text:
                raise ValueError("Invalid TTP value")
            parts.append(text)
        if extra is not None:
            parts.append(extra)
        return " ".join(parts)

    async def _command(self, command: str) -> Any:
        async with self._lock:
            writer = self._writer
            if not self._link_up or writer is None:
                raise TesiraConnectionError("Not connected to Tesira")
            future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
            self._pending = future
            self._log(">>", command)
            try:
                writer.write(command.encode() + b"\n")
                await writer.drain()
                return await asyncio.wait_for(future, self._command_timeout)
            except TimeoutError as err:
                # A late reply could be paired with the next command.
                self.last_error = f"timeout: {command}"
                self._abort()
                raise TesiraTimeoutError(f"Timeout waiting for: {command}") from err
            except OSError as err:
                self._abort()
                raise TesiraConnectionError(str(err)) from err
            finally:
                self._pending = None

    def _dispatch(self, line: str) -> None:
        if line.startswith("!"):
            match = _PUSH_RE.match(line)
            if match is None:
                _LOGGER.debug("Unparsed push line: %s", line)
            elif self._on_push is not None:
                self._on_push(match.group(1), parse_value(match.group(2)))
            return

        pending = self._pending
        if line.startswith("+OK"):
            match = _OK_RE.match(line)
            if match is None:
                _LOGGER.debug("Unparsed OK line: %s", line)
                return
            value = parse_value(match.group(1)) if match.group(1) is not None else None
            if pending is not None and not pending.done():
                pending.set_result(value)
        elif line.startswith("-ERR"):
            self.last_error = line
            if pending is not None and not pending.done():
                pending.set_exception(TesiraCommandError(line))
        # Anything else (echo, banner remnants) is ignored on purpose.

    def _log(self, direction: str, text: str) -> None:
        self.protocol_log.append(f"{direction} {text}")
        _LOGGER.debug("%s %s", direction, text)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        delay = self._backoff_start
        while True:
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - keep the loop alive
                self.last_error = str(err) or repr(err)
                _LOGGER.warning(
                    "Tesira connection to %s:%s failed: %s",
                    self._host,
                    self._port,
                    self.last_error,
                )
            else:
                delay = self._backoff_start
            finally:
                await self._teardown()
            _LOGGER.debug("Reconnecting in %.1fs", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._backoff_max)

    async def _session(self) -> None:
        await self._open()
        loop = asyncio.get_running_loop()
        self._read_task = loop.create_task(self._read_loop())
        self._link_up = True
        if self._verbose_off:
            try:
                await self._command("SESSION set verbose false")
            except TesiraCommandError:
                _LOGGER.debug("SESSION set verbose false not supported")
        if self._on_connect is not None:
            await self._on_connect()
        self._set_connected(True)
        _LOGGER.info("Connected to Tesira at %s:%s", self._host, self._port)
        # Ends with ConnectionError when the read loop stops.
        await self._read_task

    async def _teardown(self) -> None:
        self._link_up = False
        self._set_connected(False)
        read_task, self._read_task = self._read_task, None
        if read_task is not None and not read_task.done():
            read_task.cancel()
        if read_task is not None:
            await asyncio.gather(read_task, return_exceptions=True)
        await self._close()

    def _set_connected(self, value: bool) -> None:
        if self._connected == value:
            return
        self._connected = value
        if self._on_state is not None:
            self._on_state(value)

    def _abort(self) -> None:
        """Drop the transport; the read loop then ends and triggers a reconnect."""
        if self._writer is not None:
            self._writer.transport.abort()

    async def _close(self) -> None:
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _open(self) -> None:
        """Open the socket and complete the Telnet/login handshake."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), CONNECT_TIMEOUT
            )
        except TimeoutError as err:
            raise TesiraTimeoutError("Connect timeout") from err
        except OSError as err:
            raise TesiraConnectionError(str(err) or repr(err)) from err
        self._iac = IacFilter()
        self._buffer.clear()
        try:
            await asyncio.wait_for(self._handshake(), HANDSHAKE_TIMEOUT)
        except TimeoutError as err:
            raise TesiraTimeoutError("Handshake timeout") from err

    async def _handshake(self) -> None:
        if self._username is not None:
            hit = await self._expect(("login:", BANNER))
            if hit == "login:":
                await self._send_raw(self._username)
                if await self._expect(("password:", BANNER)) == "password:":
                    await self._send_raw(self._password or "")
                if await self._expect((BANNER, "login:")) != BANNER:
                    raise TesiraAuthError("Login rejected")
        elif await self._expect((BANNER, "login:")) != BANNER:
            raise TesiraAuthError("Tesira requires a login")
        self._log("<<", "banner")

    async def _send_raw(self, text: str) -> None:
        if self._writer is None:
            raise TesiraConnectionError("Not connected")
        # Credentials are deliberately not written to the protocol log.
        self._writer.write(text.encode() + b"\r\n")
        await self._writer.drain()

    async def _expect(self, markers: tuple[str, ...]) -> str:
        """Read until one of ``markers`` appears (case-insensitive)."""
        while True:
            text = self._buffer.decode("latin-1").lower()
            best: tuple[int, str] | None = None
            for marker in markers:
                pos = text.find(marker)
                if pos != -1 and (best is None or pos < best[0]):
                    best = (pos, marker)
            if best is not None:
                del self._buffer[: best[0] + len(best[1])]
                return best[1]
            await self._fill()

    async def _fill(self) -> None:
        """Read one chunk into the buffer, answering Telnet negotiation."""
        if self._reader is None or self._writer is None:
            raise TesiraConnectionError("Not connected")
        chunk = await self._reader.read(1024)
        if not chunk:
            raise TesiraConnectionError("Connection closed by Tesira")
        self._buffer.extend(strip_control(self._iac.feed(chunk)))
        if self._iac.replies:
            self._writer.write(bytes(self._iac.replies))
            self._iac.replies.clear()
            await self._writer.drain()

    async def _read_loop(self) -> None:
        try:
            while True:
                newline = self._buffer.find(b"\n")
                if newline == -1:
                    await self._fill()
                    continue
                raw = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                line = raw.decode(errors="replace").strip()
                if line:
                    self._log("<<", line)
                    self._dispatch(line)
        except asyncio.CancelledError:
            raise
        except OSError as err:
            raise TesiraConnectionError(str(err)) from err
        finally:
            self._link_up = False
            pending = self._pending
            if pending is not None and not pending.done():
                pending.set_exception(TesiraConnectionError("Disconnected"))
