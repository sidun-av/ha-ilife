"""Voice packs on ILIFE Clean laser models (A30 Pro): dp 35 `voice_data`.

A pack is a tar.gz holding `audio_cloud/NNN.wav` (PCM 16-bit mono 24 kHz), one
file per prompt number. The robot installs one when dp 35 is written with Tuya's
voice-download frame; it downloads the URL itself and checks the MD5:

    ab 01 | len u32 BE | data | sum(data) & 0xff
    data = 34 | pack id u32 BE | 00 | "0.1 " + md5 hex | url length u32 BE | url

Verified on 2026-10-24: id 51 and a LAN URL installed a custom pack. The whole
frame must fit 128 bytes: the app's own frame for the official pack is 143 bytes
(its CDN URL is long) and the robot ignores it, which is why the app times out.
The robot reports with the short frame `aa 00 07 35 | id u32 | status | progress
| sum` (status 0 failed, 1 downloading, 2 downloaded, 3 in use).

Pack directories (`<config>/ilife_voice/<pack id>/`):

    pack.json                 {"name": "...", "shuffle": true}
    audio_cloud/NNN.wav       one file for prompt NNN, or
    audio_cloud/NNN/*.wav     several candidates, one picked at random per build

Prompts a pack lacks come from the official pack (`official/`), so a pack only
needs the prompts it changes.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import random
import re
import struct
import tarfile
from dataclasses import dataclass
from pathlib import Path

VOICE_CODE = "voice_data"
OFFICIAL = "official"
OFFICIAL_URL = ("https://euimagesd2h2yqnfpu4gl5.cdn5th.com/smart/product/voice/"
                "1735178985ed8c164e482.tar.gz")
OFFICIAL_MD5 = "687bb2856aea2c2c281c441dfe4adcd2"
BUILD_DIR = ".build"
MAX_FRAME = 128
_CMD_INSTALL = 0x34
_CMD_REPORT = 0x35
_PROMPT = re.compile(r"^(\d{3})(?:\.wav)?$")
STATUSES = {0: "failed", 1: "downloading", 2: "downloaded", 3: "in_use"}


def voice_install_frame(pack_id: int, md5: str, url: str) -> bytes:
    """The dp 35 frame that installs the pack at `url` (whose MD5 is `md5`)."""
    md5 = md5.lower()
    if not re.fullmatch(r"[0-9a-f]{32}", md5):
        raise ValueError(f"not an MD5: {md5!r}")
    raw_url = url.encode()
    data = (bytes([_CMD_INSTALL]) + struct.pack(">I", pack_id) + b"\x00"
            + b"0.1 " + md5.encode() + struct.pack(">I", len(raw_url)) + raw_url)
    frame = b"\xab\x01" + struct.pack(">I", len(data)) + data + bytes([sum(data) & 0xFF])
    if len(frame) > MAX_FRAME:
        raise ValueError(
            f"voice frame is {len(frame)} bytes, the robot takes {MAX_FRAME}: "
            f"the URL ({len(raw_url)} characters) is too long")
    return frame


def voice_install_value(pack_id: int, md5: str, url: str) -> str:
    """The frame as the DP value (raw DPs travel base64-encoded)."""
    return base64.b64encode(voice_install_frame(pack_id, md5, url)).decode()


def parse_voice_report(value) -> dict | None:
    """The robot's install report from a dp 35 value, or None if it is not one."""
    try:
        raw = base64.b64decode(value) if isinstance(value, str) else bytes(value or b"")
    except (ValueError, TypeError):
        return None
    if len(raw) < 11 or raw[0] != 0xAA or raw[3] != _CMD_REPORT:
        return None
    length = int.from_bytes(raw[1:3], "big")
    body = raw[3:3 + length]
    if len(body) != length or len(raw) < 4 + length or sum(body) & 0xFF != raw[3 + length]:
        return None
    status = body[5]
    return {"id": int.from_bytes(body[1:5], "big"), "status": STATUSES.get(status, status),
            "progress": body[6]}


@dataclass(frozen=True)
class VoicePack:
    pack_id: str
    name: str
    shuffle: bool
    path: Path | None   # None: the official pack alone


def list_packs(root: Path) -> list[VoicePack]:
    """The packs under `root` (not the official one or the build directory)."""
    packs = []
    if not root.is_dir():
        return packs
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name in (OFFICIAL, BUILD_DIR) or path.name.startswith("."):
            continue
        if not (path / "audio_cloud").is_dir():
            continue
        meta = {}
        try:
            meta = json.loads((path / "pack.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if not isinstance(meta, dict):
            meta = {}
        packs.append(VoicePack(path.name, str(meta.get("name") or path.name),
                               bool(meta.get("shuffle", False)), path))
    return packs


def prompt_choices(audio_dir: Path | None) -> dict[str, list[Path]]:
    """{"NNN": [candidate files]} found in a pack's `audio_cloud`."""
    out: dict[str, list[Path]] = {}
    if audio_dir is None or not audio_dir.is_dir():
        return out
    for entry in sorted(audio_dir.iterdir()):
        match = _PROMPT.match(entry.name)
        if not match:
            continue
        if entry.is_file() and entry.suffix == ".wav":
            out.setdefault(match.group(1), []).append(entry)
        elif entry.is_dir():
            files = sorted(p for p in entry.iterdir() if p.is_file() and p.suffix == ".wav")
            if files:
                out.setdefault(match.group(1), []).extend(files)
    return out


def pick_prompts(pack: dict[str, list[Path]], official: dict[str, list[Path]],
                 seed: int) -> dict[str, Path]:
    """One file per prompt: the pack's (a random candidate), else the official one.
    The same seed always picks the same files."""
    rng = random.Random(seed)
    chosen = {}
    for number in sorted(set(pack) | set(official)):
        candidates = pack.get(number) or official.get(number)
        chosen[number] = rng.choice(candidates) if len(candidates) > 1 else candidates[0]
    return chosen


def build_pack(chosen: dict[str, Path]) -> bytes:
    """The tar.gz the robot takes: `audio_cloud/NNN.wav`, byte-identical for the
    same input (fixed mtime and owner) so a rebuild keeps its MD5."""
    if not chosen:
        raise ValueError("the voice pack has no prompts")
    buf = io.BytesIO()
    # gzip's own header carries a time too: zeroed here.
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            folder = tarfile.TarInfo("audio_cloud")
            folder.type, folder.mode, folder.mtime = tarfile.DIRTYPE, 0o755, 0
            tar.addfile(folder)
            for number in sorted(chosen):
                data = chosen[number].read_bytes()
                info = tarfile.TarInfo(f"audio_cloud/{number}.wav")
                info.size, info.mode, info.mtime = len(data), 0o644, 0
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()  # noqa: S324 — the robot's own checksum


def unpack_official(archive: bytes, dest: Path) -> int:
    """Unpack the official pack's prompts into `dest/audio_cloud`; only plain
    `audio_cloud/NNN.wav` members are taken (nothing else is written)."""
    if md5_hex(archive) != OFFICIAL_MD5:
        raise ValueError("the official voice pack's checksum does not match")
    out = dest / "audio_cloud"
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            match = re.fullmatch(r"audio_cloud/(\d{3})\.wav", member.name)
            if not match or not member.isfile():
                continue
            data = tar.extractfile(member).read()
            (out / f"{match.group(1)}.wav").write_bytes(data)
            count += 1
    return count


def build_file_name(pack_id: str, seed: int) -> str:
    """Short and URL-safe: the frame leaves the URL about 75 characters."""
    slug = re.sub(r"[^a-z0-9]", "", pack_id.lower())[:12] or "pack"
    return f"{slug}-{seed & 0xFFFFFF:06x}.tgz"
