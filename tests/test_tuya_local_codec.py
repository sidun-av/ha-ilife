"""Tuya local protocol 3.3 frame codec (no Home Assistant, no network)."""
from __future__ import annotations

import binascii
import importlib.util
import json
import pathlib
import struct
import sys
import types

_PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
_pkg = types.ModuleType("_ilife_local")
_pkg.__path__ = [str(_PKG)]
sys.modules["_ilife_local"] = _pkg
_spec = importlib.util.spec_from_file_location("_ilife_local.tuya_local", _PKG / "tuya_local.py")
tuya_local = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tuya_local
_spec.loader.exec_module(tuya_local)

KEY = b"0123456789abcdef"
FIXTURES = pathlib.Path(__file__).parent / "fixtures"

# Produced once by tinytuya 1.20.0 for seq 1, CONTROL, KEY and CONTROL_PAYLOAD.
CONTROL_PAYLOAD = {"devId": "bf0000000000000000test", "uid": "bf0000000000000000test",
                   "t": "1760000000", "dps": {"1": True}}
CONTROL_REFERENCE = bytes.fromhex(
    "000055aa000000010000000700000087332e33000000000000000000000000"
    "692cbbef37f7c782afdf7c5fe9c2479c11ae1d8da0ef348eb0298b038df701cc"
    "8fc41d5d006239f84c5db356c6ef6c98cf0545150034305f184dd405914bc331"
    "cf7b21e24b69ccb04de83805c5c654b92125e1846bd4f824d1b2e468c2399266"
    "31836d84bd28cb4b20619eb84882ca2a6586e0840000aa55")


def device_frame(seqno: int, cmd: int, payload: dict, header: bool = True) -> bytes:
    """A device->client frame: return code 0 before the (optionally headed) body."""
    body = tuya_local._encrypt(
        json.dumps(payload, separators=(",", ":")).encode(), KEY)
    if header:
        body = b"3.3" + b"\0" * 12 + body
    body = struct.pack(">I", 0) + body
    head = struct.pack(">IIII", 0x000055AA, seqno, cmd, len(body) + 8)
    crc = binascii.crc32(head + body) & 0xFFFFFFFF
    return head + body + struct.pack(">II", crc, 0x0000AA55)


def test_pack_control_matches_reference():
    frame = tuya_local.pack_message(1, tuya_local.CMD_CONTROL, CONTROL_PAYLOAD, KEY)
    assert frame == CONTROL_REFERENCE


def test_heartbeat_has_no_version_header():
    frame = tuya_local.pack_message(2, tuya_local.CMD_HEART_BEAT, {}, KEY)
    assert b"3.3" not in frame[:20]
    assert len(frame) == 16 + 16 + 8  # header, one AES block ("{}"), crc+suffix


def test_round_trip_status_frame():
    payload = {"dps": {"5": "smart"}, "t": 1}
    out = tuya_local.StreamDecoder(KEY).feed(device_frame(7, tuya_local.CMD_STATUS, payload))
    assert out == [(7, 8, payload, 0)]


def test_status_frame_without_version_header():
    payload = {"dps": {"2": True}}
    out = tuya_local.StreamDecoder(KEY).feed(
        device_frame(3, tuya_local.CMD_DP_QUERY, payload, header=False))
    assert out == [(3, 10, payload, 0)]


def test_empty_body_is_none():
    head = struct.pack(">IIII", 0x000055AA, 4, tuya_local.CMD_HEART_BEAT, 4 + 8)
    body = struct.pack(">I", 0)
    frame = head + body + struct.pack(">II", binascii.crc32(head + body) & 0xFFFFFFFF, 0xAA55)
    assert tuya_local.StreamDecoder(KEY).feed(frame) == [(4, 9, None, 0)]


def test_stream_decoder_handles_split_and_joined_frames():
    a = device_frame(1, tuya_local.CMD_STATUS, {"dps": {"1": 1}})
    b = device_frame(2, tuya_local.CMD_STATUS, {"dps": {"2": 2}})
    data = a + b
    decoder = tuya_local.StreamDecoder(KEY)
    results = []
    for chunk in (data[:10], data[10:len(a) + 5], data[len(a) + 5:]):
        results += decoder.feed(chunk)
    assert results == [(1, 8, {"dps": {"1": 1}}, 0), (2, 8, {"dps": {"2": 2}}, 0)]


def test_bad_crc_is_dropped():
    bad = bytearray(device_frame(1, tuya_local.CMD_STATUS, {"dps": {"1": 1}}))
    bad[-6] ^= 0xFF
    good = device_frame(2, tuya_local.CMD_STATUS, {"dps": {"2": 2}})
    assert tuya_local.StreamDecoder(KEY).feed(bytes(bad) + good) == [(2, 8, {"dps": {"2": 2}}, 0)]


def test_garbage_before_frame_is_skipped():
    good = device_frame(2, tuya_local.CMD_STATUS, {"dps": {"2": 2}})
    assert tuya_local.StreamDecoder(KEY).feed(b"\x01\x02\x03" + good) == [(2, 8, {"dps": {"2": 2}}, 0)]


def test_decode_discovery_fixture():
    info = tuya_local.decode_discovery((FIXTURES / "tuya_discovery_33.bin").read_bytes())
    assert info["gwId"] == "bf0000000000000000test"
    # The real broadcast carries an empty "ip"; the sender address is the host.
    assert info["ip"] == ""
    assert info["productKey"] == "5309qt4sjd4uz4qz"
    assert info["version"] == "3.3"


def test_push_without_return_code_is_decoded():
    payload = {"dps": {"5": "smart"}}
    body = b"3.3" + b"\0" * 12 + tuya_local._encrypt(
        json.dumps(payload, separators=(",", ":")).encode(), KEY)
    head = struct.pack(">IIII", 0x000055AA, 9, tuya_local.CMD_STATUS, len(body) + 8)
    crc = binascii.crc32(head + body) & 0xFFFFFFFF
    frame = head + body + struct.pack(">II", crc, 0x0000AA55)
    assert tuya_local.StreamDecoder(KEY).feed(frame) == [(9, 8, payload, None)]


def test_refusal_keeps_its_return_code_and_skips_the_plain_text_body():
    """A non-zero return code comes with a plain-text reason, not an encrypted
    payload: the frame must still come out, so the command fails at once instead
    of waiting for an acknowledgement that was already given."""
    body = struct.pack(">I", 1) + b"data format error"
    head = struct.pack(">IIII", 0x000055AA, 5, tuya_local.CMD_CONTROL, len(body) + 8)
    frame = head + body + struct.pack(
        ">II", binascii.crc32(head + body) & 0xFFFFFFFF, 0x0000AA55)
    assert tuya_local.StreamDecoder(KEY).feed(frame) == [(5, 7, None, 1)]
