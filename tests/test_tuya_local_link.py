"""TuyaLocalLink against an in-process fake device (no Home Assistant, no real LAN)."""
from __future__ import annotations

import asyncio
import binascii
import importlib.util
import json
import pathlib
import struct
import sys
import types

import pytest
import pytest_asyncio

_PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
_pkg = types.ModuleType("_ilife_link")
_pkg.__path__ = [str(_PKG)]
sys.modules["_ilife_link"] = _pkg
_spec = importlib.util.spec_from_file_location("_ilife_link.tuya_local", _PKG / "tuya_local.py")
tl = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tl
_spec.loader.exec_module(tl)

KEY = "0123456789abcdef"
KEYB = KEY.encode()
DEV = "bf0000000000000000test"


def device_frame(seqno: int, cmd: int, payload: dict | None, rc: bool = True,
                 retcode: int = 0) -> bytes:
    body = b""
    if payload is not None:
        body = b"3.3" + b"\0" * 12 + tl._encrypt(
            json.dumps(payload, separators=(",", ":")).encode(), KEYB)
    if retcode:
        body = b"data format error"
    if rc:
        body = struct.pack(">I", retcode) + body
    head = struct.pack(">IIII", 0x000055AA, seqno, cmd, len(body) + 8)
    crc = binascii.crc32(head + body) & 0xFFFFFFFF
    return head + body + struct.pack(">II", crc, 0x0000AA55)


async def read_client_frame(reader):
    head = await reader.readexactly(16)
    _, seq, cmd, length = struct.unpack(">IIII", head)
    rest = await reader.readexactly(length)
    body = rest[:-8]
    if body.startswith(b"3.3"):
        body = body[15:]
    payload = json.loads(tl._decrypt(body, KEYB)) if body else None
    return seq, cmd, payload


class FakeDevice:
    def __init__(self, dps=None):
        self.dps = dps or {"5": "smart", "8": 80}
        self.received: list[tuple[int, int, dict | None]] = []
        self.writers: list[asyncio.StreamWriter] = []
        self.queries = 0
        self.ack_control = True
        self.control_retcode = 0
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def _handle(self, reader, writer):
        self.writers.append(writer)
        try:
            while True:
                seq, cmd, payload = await read_client_frame(reader)
                self.received.append((seq, cmd, payload))
                if cmd == tl.CMD_DP_QUERY:
                    self.queries += 1
                    writer.write(device_frame(seq, cmd, {"dps": self.dps}))
                elif cmd == tl.CMD_CONTROL and self.ack_control:
                    writer.write(device_frame(seq, cmd, None, retcode=self.control_retcode))
                elif cmd == tl.CMD_HEART_BEAT:
                    writer.write(device_frame(seq, cmd, None))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass

    async def close(self):
        self.server.close()
        for w in self.writers:
            w.close()


async def until(pred, timeout=3.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not pred():
        if loop.time() > end:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


@pytest_asyncio.fixture
async def rig():
    dev = FakeDevice()
    port = await dev.start()
    got, states = [], []
    link = tl.TuyaLocalLink(DEV, KEY, "127.0.0.1", got.append, states.append, port=port)
    link.BACKOFF = (0.05, 0.05)
    link.HEARTBEAT_INTERVAL = 0.2
    link.DEAD_AFTER = 1.0
    link.ACK_TIMEOUT = 0.5
    yield dev, link, got, states
    await link.stop()
    await dev.close()


@pytest.mark.asyncio
async def test_query_on_connect_delivers_dps(rig):
    dev, link, got, states = rig
    await link.start()
    await until(lambda: link.connected)
    assert got == [{"5": "smart", "8": 80}]
    assert states == [True]
    q = [p for _, c, p in dev.received if c == tl.CMD_DP_QUERY][0]
    assert q["devId"] == DEV and q["gwId"] == DEV and q["uid"] == DEV


@pytest.mark.asyncio
async def test_push_is_delivered(rig):
    dev, link, got, states = rig
    await link.start()
    await until(lambda: link.connected)
    assert link.last_push is None
    dev.writers[0].write(device_frame(0, tl.CMD_STATUS, {"dps": {"5": "pause"}}, rc=False))
    await until(lambda: {"5": "pause"} in got)
    assert link.last_push is not None


@pytest.mark.asyncio
async def test_set_dps_sends_control_frame(rig):
    dev, link, got, states = rig
    await link.start()
    await until(lambda: link.connected)
    await link.set_dps({"2": True})
    ctl = [p for _, c, p in dev.received if c == tl.CMD_CONTROL]
    assert len(ctl) == 1 and ctl[0]["dps"] == {"2": True} and ctl[0]["devId"] == DEV


@pytest.mark.asyncio
async def test_set_dps_without_ack_raises(rig):
    dev, link, got, states = rig
    dev.ack_control = False
    await link.start()
    await until(lambda: link.connected)
    # Its own type: the coordinator must not re-send a frame that may have run.
    with pytest.raises(tl.TuyaLocalTimeout):
        await link.set_dps({"2": True})
    assert link.connected


@pytest.mark.asyncio
async def test_set_dps_refused_raises_at_once(rig):
    dev, link, got, states = rig
    dev.control_retcode = 1
    await link.start()
    await until(lambda: link.connected)
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(tl.TuyaLocalRefused) as err:
        await link.set_dps({"2": True})
    assert err.value.retcode == 1
    assert loop.time() - started < link.ACK_TIMEOUT
    assert link.connected


@pytest.mark.asyncio
async def test_heartbeat_is_sent(rig):
    dev, link, got, states = rig
    await link.start()
    await until(lambda: any(c == tl.CMD_HEART_BEAT for _, c, _ in dev.received))
    assert link.connected


@pytest.mark.asyncio
async def test_reconnects_after_server_closes(rig):
    dev, link, got, states = rig
    await link.start()
    await until(lambda: link.connected)
    dev.writers[0].close()
    await until(lambda: states == [True, False, True])
    assert dev.queries == 2
    assert len(got) == 2


@pytest.mark.asyncio
async def test_set_dps_when_disconnected_raises(rig):
    dev, link, got, states = rig
    with pytest.raises(tl.TuyaLocalError):
        await link.set_dps({"2": True})


@pytest.mark.asyncio
async def test_unreachable_host_retries_quietly(caplog):
    states = []
    link = tl.TuyaLocalLink(DEV, KEY, "127.0.0.1", lambda d: None, states.append, port=1)
    link.BACKOFF = (0.02,)
    with caplog.at_level("DEBUG", logger=tl.__name__):
        await link.start()
        await asyncio.sleep(0.3)
        await link.stop()
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and KEY not in warnings[0].getMessage()
    assert states == [] and not link.connected


@pytest.mark.asyncio
async def test_failures_count_until_connected():
    link = tl.TuyaLocalLink(DEV, KEY, "127.0.0.1", lambda d: None, lambda s: None, port=1)
    link.BACKOFF = (0.02,)
    await link.start()
    await until(lambda: link.failures >= 3)
    await link.stop()


@pytest.mark.asyncio
async def test_failures_reset_on_connect(rig):
    dev, link, got, states = rig
    link.failures = 5
    await link.start()
    await until(lambda: link.connected)
    assert link.failures == 0


DISCOVERY = (pathlib.Path(__file__).parent / "fixtures" / "tuya_discovery_33.bin").read_bytes()


def _free_udp_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _broadcast_soon(port: int, packets: list[bytes]) -> None:
    import socket
    await asyncio.sleep(0.1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for p in packets:
            s.sendto(p, ("127.0.0.1", port))


@pytest.mark.asyncio
async def test_discover_returns_sender_and_version():
    port = _free_udp_port()
    sender = asyncio.create_task(_broadcast_soon(port, [b"junk", DISCOVERY]))
    found = await tl.discover_device(DEV, timeout=2, ports=(port,))
    await sender
    assert found == ("127.0.0.1", "3.3")


@pytest.mark.asyncio
async def test_discover_ignores_other_devices_and_times_out():
    port = _free_udp_port()
    sender = asyncio.create_task(_broadcast_soon(port, [DISCOVERY]))
    assert await tl.discover_device("someotherdeviceid", timeout=0.4, ports=(port,)) is None
    await sender


def test_udp_socket_closed_when_bind_fails(monkeypatch):
    import socket

    made = []

    class FakeSocket:
        def __init__(self, *args):
            self.closed = False
            made.append(self)

        def setsockopt(self, *args):
            pass

        def bind(self, addr):
            raise OSError(98, "Address already in use")

        def setblocking(self, flag):
            pass

        def close(self):
            self.closed = True

    monkeypatch.setattr(socket, "socket", FakeSocket)
    with pytest.raises(OSError):
        tl._udp_socket(6667)
    assert len(made) == 1 and made[0].closed


@pytest.mark.asyncio
async def test_discovery_warns_once_when_no_port_can_be_bound(monkeypatch, caplog):
    def busy(port):
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(tl, "_udp_socket", busy)
    monkeypatch.setattr(tl, "_bind_warned", False)
    with caplog.at_level("DEBUG", logger=tl.__name__):
        assert await tl.discover_device(DEV, timeout=0.1, ports=(1, 2)) is None
        assert await tl.discover_device(DEV, timeout=0.1, ports=(1, 2)) is None
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and "options" in warnings[0].getMessage()
