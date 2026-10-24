"""Voice packs (dp 35 voice_data) for ILIFE Clean laser models.

The expected install frame is the one that installed a custom pack on an A30 Pro
through the cloud on 2026-10-24 (id 51, a LAN URL).
"""
from __future__ import annotations

import base64
import importlib.util
import io
import os
import pathlib
import sys
import tarfile

import pytest

_PKG = pathlib.Path(
    os.environ.get("ILIFE_PKG")
    or pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
)
_spec = importlib.util.spec_from_file_location("_ilife_voice", _PKG / "tuya_voice.py")
tuya_voice = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tuya_voice
_spec.loader.exec_module(tuya_voice)

LIVE_FRAME = bytes.fromhex(
    "ab 01 00 00 00 4d 34 00 00 00 33 00 30 2e 31 20 36 64 34 62 38 64 61 36 63 37 37 34"
    " 63 66 37 62 61 30 62 65 33 32 66 61 38 64 38 33 32 65 33 39 00 00 00 1f 68 74 74 70"
    " 3a 2f 2f 31 39 32 2e 31 36 38 2e 31 2e 31 38 30 3a 38 30 39 39 2f 6c 2e 74 67 7a a6")


def test_install_frame_matches_live_capture():
    frame = tuya_voice.voice_install_frame(
        51, "6d4b8da6c774cf7ba0be32fa8d832e39", "http://192.168.1.180:8099/l.tgz")
    assert frame == LIVE_FRAME
    assert frame[-1] == 0xA6
    assert base64.b64decode(tuya_voice.voice_install_value(
        51, "6D4B8DA6C774CF7BA0BE32FA8D832E39", "http://192.168.1.180:8099/l.tgz")) == LIVE_FRAME


def test_the_apps_official_frame_is_over_the_limit():
    # 143 bytes: what the app sends, and what the robot ignores.
    with pytest.raises(ValueError, match="143 bytes"):
        tuya_voice.voice_install_frame(50, tuya_voice.OFFICIAL_MD5, tuya_voice.OFFICIAL_URL)


def test_bad_md5_is_refused():
    with pytest.raises(ValueError):
        tuya_voice.voice_install_frame(1, "nope", "http://h/x.tgz")


def test_report_parsing():
    # dp 35 as the A30 Pro reports it with no downloaded pack.
    assert tuya_voice.parse_voice_report("qgAHNQAAAAAAADU=") == {
        "id": 0, "status": "failed", "progress": 0}
    body = bytes([0x35, 0, 0, 0, 51, 3, 100])
    raw = b"\xaa\x00\x07" + body + bytes([sum(body) & 0xFF])
    assert tuya_voice.parse_voice_report(base64.b64encode(raw).decode()) == {
        "id": 51, "status": "in_use", "progress": 100}
    assert tuya_voice.parse_voice_report(base64.b64encode(LIVE_FRAME).decode()) is None
    assert tuya_voice.parse_voice_report(base64.b64encode(raw[:-1] + b"\x00").decode()) is None
    assert tuya_voice.parse_voice_report(None) is None


def _wav(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def _official(tmp_path):
    for n in ("001", "002", "003"):
        _wav(tmp_path / "official" / "audio_cloud" / f"{n}.wav", f"official {n}")
    return tuya_voice.prompt_choices(tmp_path / "official" / "audio_cloud")


def test_pack_fills_missing_prompts_from_the_official_one(tmp_path):
    official = _official(tmp_path)
    _wav(tmp_path / "leather" / "audio_cloud" / "002.wav", "leather 002")
    pack = tuya_voice.prompt_choices(tmp_path / "leather" / "audio_cloud")
    chosen = tuya_voice.pick_prompts(pack, official, seed=1)
    assert {n: p.read_text() for n, p in chosen.items()} == {
        "001": "official 001", "002": "leather 002", "003": "official 003"}


def test_candidates_are_picked_by_seed(tmp_path):
    official = _official(tmp_path)
    for k in range(5):
        _wav(tmp_path / "witcher" / "audio_cloud" / "001" / f"{k}.wav", f"geralt {k}")
    pack = tuya_voice.prompt_choices(tmp_path / "witcher" / "audio_cloud")
    picks = {tuya_voice.pick_prompts(pack, official, seed)["001"].read_text() for seed in range(40)}
    assert len(picks) > 1 and picks <= {f"geralt {k}" for k in range(5)}
    assert (tuya_voice.pick_prompts(pack, official, 7)
            == tuya_voice.pick_prompts(pack, official, 7))


def test_build_is_reproducible_and_laid_out_like_the_official(tmp_path):
    chosen = tuya_voice.pick_prompts({}, _official(tmp_path), 0)
    archive = tuya_voice.build_pack(chosen)
    assert archive == tuya_voice.build_pack(chosen)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        assert tar.getnames() == ["audio_cloud", "audio_cloud/001.wav",
                                  "audio_cloud/002.wav", "audio_cloud/003.wav"]
        assert tar.extractfile("audio_cloud/002.wav").read() == b"official 002"
    with pytest.raises(ValueError):
        tuya_voice.build_pack({})


def test_list_packs(tmp_path):
    _official(tmp_path)
    _wav(tmp_path / "leather" / "audio_cloud" / "001.wav", "x")
    (tmp_path / "leather" / "pack.json").write_text('{"name": "Кожаные", "shuffle": false}')
    _wav(tmp_path / "witcher" / "audio_cloud" / "001" / "0.wav", "x")
    (tmp_path / "witcher" / "pack.json").write_text('{"name": "Ведьмак", "shuffle": true}')
    (tmp_path / "empty").mkdir()
    _wav(tmp_path / ".build" / "audio_cloud" / "001.wav", "x")
    packs = tuya_voice.list_packs(tmp_path)
    assert [(p.pack_id, p.name, p.shuffle) for p in packs] == [
        ("leather", "Кожаные", False), ("witcher", "Ведьмак", True)]
    assert tuya_voice.list_packs(tmp_path / "missing") == []


def test_unpack_official_checks_the_md5(tmp_path):
    with pytest.raises(ValueError):
        tuya_voice.unpack_official(b"not the pack", tmp_path)


def test_build_file_name_is_short():
    name = tuya_voice.build_file_name("Witcher pack!", 0x123456789)
    assert name == "witcherpack-456789.tgz"
