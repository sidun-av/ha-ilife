"""Voice packs in a real Home Assistant: choosing one sends the install frame with
a URL Home Assistant serves, and a shuffled pack is rebuilt after a clean."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import struct
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ilife import voice as voice_module
from harness import DEVICE_ID, FakeClient, FakeLink, coordinator, entity_id, make_entry

BASE_URL = "http://192.168.1.100:8123"


def _wav(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())


@pytest.fixture
def voice_dir(hass, tmp_path):
    """A config directory with the official prompts already fetched, a plain pack
    and one with several candidates per prompt."""
    hass.config.config_dir = str(tmp_path)
    hass.config.internal_url = BASE_URL
    root = tmp_path / "ilife_voice"
    for n in ("001", "002", "003"):
        _wav(root / "official" / "audio_cloud" / f"{n}.wav", f"official {n}")
    _wav(root / "leather" / "audio_cloud" / "001.wav", "leather 001")
    (root / "leather" / "pack.json").write_text('{"name": "Кожаные", "shuffle": false}')
    for k in range(6):
        _wav(root / "witcher" / "audio_cloud" / "002" / f"{k}.wav", f"geralt {k}")
    (root / "witcher" / "pack.json").write_text('{"name": "Ведьмак", "shuffle": true}')
    return root


def _frame(value):
    raw = base64.b64decode(value)
    assert raw[:2] == b"\xab\x01" and raw[6] == 0x34
    data = raw[6:-1]
    assert sum(data) & 0xFF == raw[-1]
    pack_id = struct.unpack(">I", data[1:5])[0]
    md5 = data[10:42].decode()
    url_len = struct.unpack(">I", data[42:46])[0]
    return pack_id, md5, data[46:46 + url_len].decode()


async def _setup(hass, *, local=False):
    entry = make_entry(hass, local=local)
    with patch.object(voice_module, "async_get_clientsession",
                      side_effect=AssertionError("the official pack must not be fetched")):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def _select(hass, option):
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": entity_id(hass, "select", "voice_pack"), "option": option}, blocking=True)


def _voice_writes(sent):
    return [c["value"] for batch in sent if isinstance(batch, list)
            for c in batch if c["code"] == "voice_data"]


async def test_choosing_a_pack_sends_the_install_frame(hass, voice_dir):
    await _setup(hass)
    state = hass.states.get(entity_id(hass, "select", "voice_pack"))
    assert state.attributes["options"] == ["official", "Кожаные", "Ведьмак"]

    await _select(hass, "Кожаные")
    pack_id, md5, url = _frame(_voice_writes(FakeClient.instances[-1].sent)[-1])
    assert pack_id == voice_module.FIRST_PACK_ID + 1
    assert url.startswith(f"{BASE_URL}/ilife_voice/leather-") and url.endswith(".tgz")
    built = voice_dir / ".build" / url.rsplit("/", 1)[1]
    assert hashlib.md5(built.read_bytes()).hexdigest() == md5
    assert hass.states.get(entity_id(hass, "select", "voice_pack")).state == "Кожаные"
    record = coordinator(hass).cache.get(DEVICE_ID)
    assert record["voice_pack"] == "leather" and record["voice_id"] == pack_id

    await _select(hass, "official")
    pack_id2, _md5, url2 = _frame(_voice_writes(FakeClient.instances[-1].sent)[-1])
    assert pack_id2 == pack_id + 1 and "/official-" in url2


async def test_a_long_or_https_url_is_refused(hass, voice_dir):
    await _setup(hass)
    hass.config.internal_url = "https://ha.example.com:8443"
    with pytest.raises(HomeAssistantError, match="plain HTTP"):
        await _select(hass, "Кожаные")
    hass.config.internal_url = "http://" + "h" * 60 + ".local:8123"
    with pytest.raises(HomeAssistantError, match="too long"):
        await _select(hass, "Кожаные")
    assert not _voice_writes(FakeClient.instances[-1].sent)


async def test_shuffled_pack_is_rebuilt_after_a_clean(hass, voice_dir, cached_robot):
    cached_robot()
    await _setup(hass, local=True)
    link = FakeLink.instances[-1]
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity_id(hass, "switch", "shuffle_voice")},
        blocking=True)
    await _select(hass, "Ведьмак")
    first = [f["voice_data"] for f in link.frames if "voice_data" in f]
    assert len(first) == 1

    link.push(status="smart")
    link.push(status="goto_charge")
    for _ in range(50):
        await asyncio.sleep(0.02)
        await hass.async_block_till_done()
        if len([f for f in link.frames if "voice_data" in f]) == 2:
            break
    writes = [f["voice_data"] for f in link.frames if "voice_data" in f]
    assert len(writes) == 2
    assert _frame(writes[1])[0] == _frame(writes[0])[0] + 1

    # Docked afterwards: the same run, no second rebuild.
    link.push(status="base_charging")
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()
    assert len([f for f in link.frames if "voice_data" in f]) == 2


async def test_no_shuffle_after_a_clean_when_off(hass, voice_dir, cached_robot):
    cached_robot()
    await _setup(hass, local=True)
    link = FakeLink.instances[-1]
    await _select(hass, "Ведьмак")
    link.push(status="smart")
    link.push(status="goto_charge")
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()
    assert len([f for f in link.frames if "voice_data" in f]) == 1


async def test_shuffle_button_needs_a_shuffled_pack(hass, voice_dir):
    await _setup(hass)
    await _select(hass, "Кожаные")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id(hass, "button", "shuffle_voice_now")},
            blocking=True)
    await _select(hass, "Ведьмак")
    before = len(_voice_writes(FakeClient.instances[-1].sent))
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id(hass, "button", "shuffle_voice_now")},
        blocking=True)
    assert len(_voice_writes(FakeClient.instances[-1].sent)) == before + 1


async def test_official_pack_is_fetched_once_when_missing(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    hass.config.internal_url = BASE_URL
    await _setup(hass)
    voice = coordinator(hass).voice
    with patch.object(voice_module, "async_get_clientsession",
                      side_effect=RuntimeError("offline")):
        with pytest.raises(HomeAssistantError, match="official voice pack"):
            await _select(hass, "official")
    assert voice.current is None
