"""Tuya local protocol 3.3 over the LAN.

Codec part: framing, AES-128-ECB, discovery packets.
Link part: persistent TCP connection with push, heartbeat and reconnect.
No Home Assistant imports.
"""
from __future__ import annotations

import asyncio
import binascii
import hashlib
import json
import logging
import struct
import time
from collections.abc import Callable
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

CMD_CONTROL = 0x07
CMD_STATUS = 0x08
CMD_HEART_BEAT = 0x09
CMD_DP_QUERY = 0x0A

UDP_KEY = hashlib.md5(b"yGAdlopoPVldABfn").digest()  # noqa: S324 - protocol constant

_PREFIX = 0x000055AA
_SUFFIX = 0x0000AA55
_PREFIX_BYTES = struct.pack(">I", _PREFIX)
_VERSION_HEADER = b"3.3" + b"\x00" * 12
_NO_HEADER_CMDS = (CMD_DP_QUERY, CMD_HEART_BEAT)
_HEAD = struct.Struct(">IIII")  # prefix, seqno, cmd, length
_MAX_FRAME = 64 * 1024


def _encrypt(data: bytes, key: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()  # noqa: S305
    return enc.update(padder.update(data) + padder.finalize()) + enc.finalize()


def _decrypt(data: bytes, key: bytes) -> bytes:
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()  # noqa: S305
    unpadder = padding.PKCS7(128).unpadder()
    plain = dec.update(data) + dec.finalize()
    return unpadder.update(plain) + unpadder.finalize()


def pack_message(seqno: int, cmd: int, payload: dict | None, key: bytes) -> bytes:
    """Build a client->device frame."""
    body = b""
    if payload is not None:
        body = _encrypt(json.dumps(payload, separators=(",", ":")).encode(), key)
        if cmd not in _NO_HEADER_CMDS:
            body = _VERSION_HEADER + body
    head = _HEAD.pack(_PREFIX, seqno, cmd, len(body) + 8)
    crc = binascii.crc32(head + body) & 0xFFFFFFFF
    return head + body + struct.pack(">II", crc, _SUFFIX)


class StreamDecoder:
    """Reassembles device->client frames from a TCP byte stream."""

    def __init__(self, key: bytes) -> None:
        self._key = key
        self._buf = b""

    def feed(self, data: bytes) -> list[tuple[int, int, dict | None]]:
        self._buf += data
        out: list[tuple[int, int, dict | None]] = []
        while True:
            start = self._buf.find(_PREFIX_BYTES)
            if start < 0:
                # keep a possible partial prefix at the tail
                self._buf = self._buf[-3:]
                break
            if start:
                self._buf = self._buf[start:]
            if len(self._buf) < _HEAD.size:
                break
            _, seqno, cmd, length = _HEAD.unpack_from(self._buf)
            if length < 8 or length > _MAX_FRAME:
                self._buf = self._buf[4:]
                continue
            total = _HEAD.size + length
            if len(self._buf) < total:
                break
            frame, self._buf = self._buf[:total], self._buf[total:]
            crc, suffix = struct.unpack(">II", frame[-8:])
            if suffix != _SUFFIX or crc != binascii.crc32(frame[:-8]) & 0xFFFFFFFF:
                _LOGGER.debug("Dropping Tuya frame with bad CRC (seq %s, cmd %s)", seqno, cmd)
                continue
            try:
                out.append((seqno, cmd, self._decode_body(frame[_HEAD.size:-8])))
            except Exception:  # noqa: BLE001 - one bad frame must not kill the link
                _LOGGER.debug("Dropping undecodable Tuya frame (seq %s, cmd %s)", seqno, cmd)
        return out

    def _decode_body(self, body: bytes) -> dict | None:
        # Replies/acks carry a 4-byte return code; some firmware's unsolicited
        # STATUS pushes start straight with the "3.3" header instead.
        if not body.startswith(b"3.3"):
            body = body[4:]
        if body.startswith(b"3.3"):
            body = body[len(_VERSION_HEADER):]
        if not body:
            return None
        return json.loads(_decrypt(body, self._key))


def decode_discovery(packet: bytes) -> dict[str, Any]:
    """Decode a UDP broadcast (port 6666) into its JSON dict."""
    body = packet[_HEAD.size + 4:-8]  # skip head and return code, drop crc+suffix
    return json.loads(_decrypt(body, UDP_KEY))


DISCOVERY_PORTS = (6666, 6667)


def _decode_any_discovery(packet: bytes) -> dict | None:
    """Encrypted (6667, protocol 3.3+) or plain (6666, 3.1) broadcast; None if neither."""
    try:
        info = decode_discovery(packet)
    except Exception:  # noqa: BLE001 - not an encrypted broadcast
        try:
            info = json.loads(packet[_HEAD.size + 4:-8])
        except Exception:  # noqa: BLE001
            return None
    return info if isinstance(info, dict) else None


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, device_id: str, found: asyncio.Future) -> None:
        self._device_id = device_id
        self._found = found

    def datagram_received(self, data: bytes, addr) -> None:
        info = _decode_any_discovery(data)
        if info and info.get("gwId") == self._device_id and not self._found.done():
            # The robot broadcasts "ip": ""; the sender address is the host.
            self._found.set_result((addr[0], str(info.get("version") or "")))


def _udp_socket(port: int):
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", port))
        sock.setblocking(False)
    except OSError:
        sock.close()
        raise
    return sock


async def discover_device(
    device_id: str, timeout: float = 10, ports: tuple[int, ...] = DISCOVERY_PORTS
) -> tuple[str, str] | None:
    """Listen for the device's UDP broadcast: (host, protocol version), or None."""
    loop = asyncio.get_running_loop()
    found: asyncio.Future = loop.create_future()
    transports = []
    try:
        for port in ports:
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: _DiscoveryProtocol(device_id, found), sock=_udp_socket(port))
            except OSError as err:
                _LOGGER.debug("Cannot listen for Tuya discovery on UDP %s: %s", port, err)
                continue
            transports.append(transport)
        if not transports:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(found), timeout)
        except asyncio.TimeoutError:
            return None
    finally:
        for transport in transports:
            transport.close()
        if not found.done():
            found.cancel()


async def discover(
    device_id: str, timeout: float = 10, ports: tuple[int, ...] = DISCOVERY_PORTS
) -> str | None:
    """The device's LAN address from its UDP broadcast, or None on timeout."""
    found = await discover_device(device_id, timeout, ports)
    return found[0] if found else None


class TuyaLocalError(Exception):
    """Local command could not be delivered or acknowledged."""


class TuyaLocalLink:
    """Persistent protocol-3.3 connection to one device."""

    HEARTBEAT_INTERVAL = 10.0
    DEAD_AFTER = 25.0
    BACKOFF = (1.0, 2.0, 5.0, 10.0, 30.0)
    ACK_TIMEOUT = 5.0
    CONNECT_TIMEOUT = 5.0

    def __init__(
        self,
        device_id: str,
        local_key: str,
        host: str,
        on_dps: Callable[[dict[str, Any]], None],
        on_state: Callable[[bool], None],
        port: int = 6668,
    ) -> None:
        self._device_id = device_id
        self._key = local_key.encode()
        self.host = host
        self._port = port
        self._on_dps = on_dps
        self._on_state = on_state
        self.connected = False
        self.last_push: float | None = None
        # Connection attempts in a row that never got an answer; the owner rediscovers
        # the host after a few (the robot's DHCP address may have changed).
        self.failures = 0
        self._task: asyncio.Task | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._seq = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._warned = False

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def set_dps(self, dps: dict[str, Any]) -> None:
        if not self.connected or self._writer is None:
            raise TuyaLocalError("local link is not connected")
        payload = {
            "devId": self._device_id,
            "uid": self._device_id,
            "t": str(int(time.time())),
            "dps": dps,
        }
        seq = self._next_seq()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[seq] = fut
        try:
            await self._send(seq, CMD_CONTROL, payload)
            await asyncio.wait_for(fut, self.ACK_TIMEOUT)
        except asyncio.TimeoutError as err:
            raise TuyaLocalError("no acknowledgement from device") from err
        except OSError as err:
            raise TuyaLocalError(f"send failed: {err.__class__.__name__}") from err
        finally:
            self._pending.pop(seq, None)

    # -- internals ---------------------------------------------------------

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        return self._seq

    async def _send(self, seq: int, cmd: int, payload: dict | None) -> None:
        writer = self._writer
        if writer is None:
            raise TuyaLocalError("local link is not connected")
        writer.write(pack_message(seq, cmd, payload, self._key))
        await writer.drain()

    async def _run(self) -> None:
        attempt = 0
        while True:
            reached = False
            try:
                reached = await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - keep reconnecting
                reason = err.__class__.__name__
            else:
                reason = "connection closed"
            if reached:
                attempt = 0
            else:
                self.failures += 1
            if self._warned:
                _LOGGER.debug("Local link to %s down (%s)", self.host, reason)
            else:
                self._warned = True
                _LOGGER.warning("Local link to %s lost (%s); retrying in background", self.host, reason)
            delay = self.BACKOFF[min(attempt, len(self.BACKOFF) - 1)]
            attempt += 1
            await asyncio.sleep(delay)

    def _set_connected(self, value: bool) -> None:
        if self.connected == value:
            return
        self.connected = value
        try:
            self._on_state(value)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("on_state callback failed")

    def _deliver(self, dps: Any) -> None:
        if not isinstance(dps, dict):
            return
        try:
            self._on_dps(dps)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("on_dps callback failed")

    async def _session(self) -> bool:
        """One connection lifetime. Returns True if it became fully connected."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self._port), self.CONNECT_TIMEOUT
        )
        self._writer = writer
        decoder = StreamDecoder(self._key)
        reached = False
        try:
            await self._send(
                self._next_seq(),
                CMD_DP_QUERY,
                {
                    "gwId": self._device_id,
                    "devId": self._device_id,
                    "uid": self._device_id,
                    "t": str(int(time.time())),
                },
            )
            now = time.monotonic()
            last_rx = last_hb = now
            query_deadline = now + self.ACK_TIMEOUT
            while True:
                now = time.monotonic()
                if now - last_rx > self.DEAD_AFTER:
                    raise TuyaLocalError("device silent")
                if not self.connected and now > query_deadline:
                    raise TuyaLocalError("no reply to query")
                if now - last_hb >= self.HEARTBEAT_INTERVAL:
                    await self._send(
                        self._next_seq(),
                        CMD_HEART_BEAT,
                        {"gwId": self._device_id, "devId": self._device_id},
                    )
                    last_hb = now
                wait = max(0.01, last_hb + self.HEARTBEAT_INTERVAL - now)
                if not self.connected:
                    wait = min(wait, max(0.01, query_deadline - now))
                try:
                    data = await asyncio.wait_for(reader.read(4096), wait)
                except asyncio.TimeoutError:
                    continue
                if not data:
                    return reached
                last_rx = time.monotonic()
                for seq, cmd, payload in decoder.feed(data):
                    if cmd == CMD_DP_QUERY:
                        if payload:
                            self._deliver(payload.get("dps"))
                        if not self.connected:
                            self._warned = False
                            self.failures = 0
                            reached = True
                            self._set_connected(True)
                    elif cmd == CMD_STATUS:
                        self.last_push = time.monotonic()
                        if payload:
                            self._deliver(payload.get("dps"))
                    elif cmd == CMD_CONTROL:
                        fut = self._pending.get(seq)
                        if fut is not None and not fut.done():
                            fut.set_result(None)
        finally:
            self._writer = None
            self._set_connected(False)
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(TuyaLocalError("connection lost"))
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
