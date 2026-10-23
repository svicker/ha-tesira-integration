"""Async Telnet/TCP client for Biamp Tesira TTP protocol."""
from __future__ import annotations

import asyncio
import logging
import re
import socket
from collections.abc import Callable
from typing import Any

from .const import (
    KEEP_ALIVE_INTERVAL,
    RECONNECT_INTERVAL,
    TTP_ERROR,
    TTP_OK,
    TTP_PUBLISH_PREFIX,
    TTP_SESSION_READY,
)

_LOGGER = logging.getLogger(__name__)

# Matches:  +OK value:"..." / +OK "value":X / +OK value:X / +OK (no value)
# Tesira firmwares vary in whether "value" is quoted as a JSON-style key.
_OK_RE    = re.compile(r'^\+OK(?:\s+"?value"?\s*:\s*(.+))?$')
# Matches subscription publishes:  ! InstanceTag attribute value
_PUB_RE   = re.compile(r'^! "?([^"]+)"? ([a-zA-Z]+) (.+)$')

# ---------------------------------------------------------------------------
# Telnet IAC (Interpret As Command) handling
# ---------------------------------------------------------------------------
# The Tesira TTP service speaks real Telnet, including option negotiation
# (IAC DO/DONT/WILL/WONT ...). A plain TCP socket (asyncio.open_connection)
# does not strip these control sequences, so they end up mixed into the text
# stream and break line-based parsing (e.g. the "Welcome to the Tesira"
# banner is never recognized). We filter IAC sequences out of the incoming
# byte stream and reply WONT/DONT to refuse all offered options, which is
# sufficient to get a clean line-oriented text stream.

IAC  = 0xFF  # Interpret As Command
DONT = 0xFE
DO   = 0xFD
WONT = 0xFC
WILL = 0xFB
SB   = 0xFA  # Subnegotiation begin
SE   = 0xF0  # Subnegotiation end


class _IacFilter:
    """Strips Telnet IAC sequences from a byte stream and auto-replies.

    Feed raw bytes in via `feed()`; cleaned bytes (with IAC sequences
    removed) are appended to `self.buffer`. Any negotiation replies that
    need to be sent back are appended to `self.replies` for the caller to
    write to the transport.
    """

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.replies = bytearray()
        self._state = "data"      # data | iac | negotiate | subneg | subneg_iac
        self._neg_cmd: int | None = None

    def feed(self, data: bytes) -> None:
        for byte in data:
            if self._state == "data":
                if byte == IAC:
                    self._state = "iac"
                else:
                    self.buffer.append(byte)

            elif self._state == "iac":
                if byte == IAC:
                    # Escaped 0xFF in data
                    self.buffer.append(byte)
                    self._state = "data"
                elif byte in (DO, DONT, WILL, WONT):
                    self._neg_cmd = byte
                    self._state = "negotiate"
                elif byte == SB:
                    self._state = "subneg"
                else:
                    # Other IAC commands (NOP, AYT, etc.) – ignore
                    self._state = "data"

            elif self._state == "negotiate":
                # byte = option code being negotiated
                self._reply(self._neg_cmd, byte)
                self._neg_cmd = None
                self._state = "data"

            elif self._state == "subneg":
                if byte == IAC:
                    self._state = "subneg_iac"
                # else: consume subnegotiation data silently

            elif self._state == "subneg_iac":
                if byte == SE:
                    self._state = "data"
                elif byte == IAC:
                    self._state = "subneg"
                else:
                    self._state = "subneg"

    def _reply(self, cmd: int, option: int) -> None:
        """Refuse all negotiated options (we just want plain text mode)."""
        if cmd in (DO, WILL):
            # Server wants us to do something, or offers to do something.
            # Politely decline everything to keep the stream as plain text.
            response = WONT if cmd == DO else DONT
            self.replies.extend([IAC, response, option])
        # If server says DONT/WONT, no reply needed.


class TesiraClient:
    """Persistent async TCP client for the Tesira TTP protocol."""

    def __init__(
        self,
        host: str,
        port: int,
        on_state_change: Callable[[str, str, Any], None],
    ) -> None:
        self._host = host
        self._port = port
        self._on_state_change = on_state_change

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._running = False

        # Pending commands: asyncio.Future keyed by sequence
        self._pending: asyncio.Future | None = None
        self._cmd_lock = asyncio.Lock()

        self._read_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None

        # Telnet IAC filter + line buffer for _read_filtered_line()
        self._iac = _IacFilter()
        self._linebuf = bytearray()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the client (connect + begin background tasks)."""
        self._running = True
        await self._connect()

    async def stop(self) -> None:
        """Disconnect and stop all background tasks."""
        self._running = False
        for task in (self._read_task, self._keepalive_task, self._reconnect_task):
            if task and not task.done():
                task.cancel()
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass

    @property
    def connected(self) -> bool:
        return self._connected

    async def get_attribute(self, instance: str, attribute: str, channel: int | None = 1) -> Any:
        """Send a GET command and return the parsed value.

        If channel is None, no channel argument is sent (used for
        block-level attributes like a Source Selector's sourceSelection,
        which is not addressed per-channel).
        """
        if channel is None:
            cmd = f'"{instance}" get {attribute}'
        else:
            cmd = f'"{instance}" get {attribute} {channel}'
        response = await self._send_command(cmd)
        return response

    async def set_attribute(self, instance: str, attribute: str, value: Any, channel: int | None = 1) -> None:
        """Send a SET command.

        If channel is None, no channel argument is sent (used for
        block-level attributes like a Source Selector's sourceSelection,
        which is not addressed per-channel).
        """
        if channel is None:
            cmd = f'"{instance}" set {attribute} {value}'
        else:
            cmd = f'"{instance}" set {attribute} {channel} {value}'
        await self._send_command(cmd)

    async def subscribe(self, instance: str, attribute: str, publish_token: str) -> None:
        """Subscribe to attribute change notifications."""
        cmd = f'"{instance}" subscribe {attribute} "{publish_token}"'
        await self._send_command(cmd)

    async def unsubscribe(self, instance: str, attribute: str, publish_token: str) -> None:
        cmd = f'"{instance}" unsubscribe {attribute} "{publish_token}"'
        await self._send_command(cmd)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        try:
            _LOGGER.debug("Connecting to Tesira at %s:%s", self._host, self._port)
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=10,
            )

            # Reset IAC filter state for a fresh connection
            self._iac = _IacFilter()
            self._linebuf.clear()

            # Wait for welcome banner (IAC sequences are filtered out)
            while True:
                line = await asyncio.wait_for(self._read_filtered_line(), timeout=10)
                if line is None:
                    raise ConnectionError("Connection closed before banner")
                text = line.decode(errors="replace").strip()
                if text:
                    _LOGGER.debug("TESIRA banner: %s", text)
                if TTP_SESSION_READY in text:
                    break

            self._connected = True
            _LOGGER.info("Connected to Tesira at %s:%s", self._host, self._port)

            self._read_task = asyncio.create_task(self._read_loop())
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

            # Notify integration to set up subscriptions / read initial state
            self._on_state_change("__connected__", "", True)

        except Exception as exc:
            _LOGGER.warning(
                "Tesira connection failed: %s – retrying in %ss",
                exc or repr(exc),
                RECONNECT_INTERVAL,
            )
            self._connected = False
            self._reconnect_task = asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        await asyncio.sleep(RECONNECT_INTERVAL)
        if self._running:
            await self._connect()

    # ------------------------------------------------------------------
    # Filtered, line-oriented reading (strips Telnet IAC sequences)
    # ------------------------------------------------------------------

    async def _read_filtered_line(self) -> bytes | None:
        """Read a single line from the socket with Telnet IAC sequences
        stripped out and negotiation replies sent automatically.

        Returns the line (without trailing newline), or None on EOF.
        """
        while True:
            # Do we already have a full line buffered?
            nl_idx = self._linebuf.find(b"\n")
            if nl_idx != -1:
                line = bytes(self._linebuf[:nl_idx])
                del self._linebuf[: nl_idx + 1]
                # Strip trailing \r if present (CRLF)
                if line.endswith(b"\r"):
                    line = line[:-1]
                return line

            chunk = await self._reader.read(1024)
            if not chunk:
                # EOF – return whatever's left, or None if nothing
                if self._linebuf:
                    line = bytes(self._linebuf)
                    self._linebuf.clear()
                    return line
                return None

            self._iac.feed(chunk)

            # Send any negotiation replies immediately
            if self._iac.replies:
                self._writer.write(bytes(self._iac.replies))
                await self._writer.drain()
                self._iac.replies.clear()

            if self._iac.buffer:
                self._linebuf.extend(self._iac.buffer)
                self._iac.buffer.clear()

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        """Read lines from Tesira and dispatch responses / publishes."""
        try:
            while self._connected:
                line = await self._read_filtered_line()
                if line is None:
                    break
                text = line.decode(errors="replace").strip()
                if not text:
                    continue
                _LOGGER.debug("TESIRA <<  %s", text)
                self._dispatch(text)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            _LOGGER.error("Tesira read error: %s", exc)
        finally:
            self._connected = False
            _LOGGER.warning("Tesira connection lost – scheduling reconnect")
            if self._pending and not self._pending.done():
                self._pending.set_exception(ConnectionError("Disconnected"))
            if self._running:
                self._reconnect_task = asyncio.create_task(self._reconnect())

    async def _keepalive_loop(self) -> None:
        """Keep the TCP connection alive.

        We deliberately avoid sending any TTP command here: the exact set
        of supported attributes (DEVICE get version, SESSION get hostname,
        etc.) varies between Tesira firmware versions and an unsupported
        command produces log warnings (-ERR ... not supported) or, worse,
        a silent timeout if the device doesn't reply at all.

        The TTP/Telnet session itself does not require periodic traffic to
        stay open as long as the underlying TCP connection is alive, so we
        enable TCP keepalive on the socket once and otherwise do nothing.
        If a device/firewall still drops idle connections after some time,
        the read loop will detect the EOF and trigger a reconnect.
        """
        try:
            sock = self._writer.get_extra_info("socket") if self._writer else None
            if sock is not None:
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                except OSError:
                    pass

            while self._connected:
                await asyncio.sleep(KEEP_ALIVE_INTERVAL)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Command sending
    # ------------------------------------------------------------------

    async def _send_command(self, cmd: str, timeout: float = 5.0) -> Any:
        """Send a single TTP command and await its +OK / -ERR response."""
        async with self._cmd_lock:
            if not self._connected or not self._writer:
                raise ConnectionError("Not connected to Tesira")

            self._pending = asyncio.get_event_loop().create_future()
            raw = (cmd + "\n").encode()
            _LOGGER.debug("TESIRA >>  %s", cmd)
            self._writer.write(raw)
            await self._writer.drain()

            try:
                result = await asyncio.wait_for(self._pending, timeout=timeout)
            except asyncio.TimeoutError:
                _LOGGER.warning("Tesira command timed out: %s", cmd)
                return None
            finally:
                self._pending = None
            return result

    # ------------------------------------------------------------------
    # Response dispatching
    # ------------------------------------------------------------------

    def _dispatch(self, text: str) -> None:
        # Subscription publish
        if text.startswith(TTP_PUBLISH_PREFIX):
            self._handle_publish(text)
            return

        # +OK response
        m = _OK_RE.match(text)
        if m:
            value = self._parse_value(m.group(1)) if m.group(1) else True
            if self._pending and not self._pending.done():
                self._pending.set_result(value)
            return

        # -ERR response
        if text.startswith(TTP_ERROR):
            _LOGGER.warning("Tesira error: %s", text)
            if self._pending and not self._pending.done():
                self._pending.set_result(None)
            return

    def _handle_publish(self, text: str) -> None:
        m = _PUB_RE.match(text)
        if not m:
            return
        instance, attribute, raw_value = m.group(1), m.group(2), m.group(3)
        value = self._parse_value(raw_value)
        _LOGGER.debug("Publish: %s.%s = %s", instance, attribute, value)
        self._on_state_change(instance, attribute, value)

    @staticmethod
    def _parse_value(raw: str) -> Any:
        """Parse a TTP value string into a Python type."""
        if raw is None:
            return None
        raw = raw.strip().strip('"')
        if raw.lower() == "true":
            return True
        if raw.lower() == "false":
            return False
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass
        return raw
