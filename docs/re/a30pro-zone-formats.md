# ILIFE A30 Pro (Tuya `5309qt4sjd4uz4qz`): zone, spot, no-go, wall and related DP formats

Offline research, 2026-10-18. No robot was contacted and no credentials were used.

## TL;DR

- **The ILIFE Clean (Tuya) app does not contain the encoders.** `com.iliferobot.clean` 1.0.8 is a
  stock Tuya OEM shell. The A30 Pro panel is a Tuya mini-app that is downloaded at runtime. None of
  the DP codes appear anywhere in the APK.
- **ILIFE's own Aliyun app (`com.ilife.home.global` 1.9.43, "ILIFEHOME") does contain them**, as
  native Java for ILIFE's Aliyun-cloud laser robots (X9/X800/X1000 families). It uses the *same
  property identifiers*: `CleanAreaData`, `CleanPartitionData`, `VirtualWallData`, `MapRoomInfo1..3`,
  `CleanSettings*`, `SaveMap`, `AddRoomDoor`, `DeleteRoomDoor`, `AppRemind`, `InitStatus`.
- Two values the integration already decodes match ILIFE's Aliyun encoding:
  - `MapRoomInfo*` is byte-identical: base64 of `"<mapId>,<mapName>,<roomId>,<name>,…"`.
  - `CleanPartitionData` is the Aliyun struct `{Enable, CleanLoop, PartitionData}` flattened as
    `u8 Enable, u8 CleanLoop, u32 BE PartitionData`.

  So the A30 Pro's Tuya firmware is a port of ILIFE's Aliyun firmware. Its string DPs carry the
  Aliyun payloads, and each Aliyun struct is flattened field by field into bytes.
- **What the code verifies** (the Aliyun side): the inner geometry encoding. Points are big-endian
  s16 `(x, y)` pairs, in **map cells** relative to the robot's map origin, with **y pointing up**
  (the app stores `-screen_y`). A rectangle is four corners. Passes are in the `CleanLoop` byte: the
  low nibble is the requested passes and the high nibble the passes done. Writing the DP with
  `Enable = 1` starts the job by itself.
- **What is inferred, not verified:** exactly how the Tuya port wraps those payloads in dp
  139/140/141/142/147/146. That covers the header bytes, the zone count, and whether walls and
  zones are padded to a fixed number of slots. The Tuya mini-app was not obtainable offline. One
  draw-and-read capture per DP, listed at the end, settles each one.

## Sources

| What | Where |
|---|---|
| ILIFEHOME APK | APKPure XAPK `com.ilife.home.global` 1.9.43 (vc 123), base APK sha256 `e3315790…faa6`. Decompiled with jadx 1.5.1: `classes3.dex` and `classes4.dex` |
| ILIFE Clean APK | APKPure XAPK `com.iliferobot.clean` 1.0.8 (vc 9), sha256 `122f8b92…f153`. No ILIFE panel code; only Tuya `kit_js/miniapp_SweeperKit.js` |
| Property names | `com/aliyun/iot/aep/sdk/contant/EnvConfigure.java` |
| Zone (rectangle) clean | `com/ilife/home/robot/view/helper/helperx9/CleanAreaHelper.java` (`getCleanAreaData`, `setCleanArea`); `com/aliyun/iot/aep/sdk/bean/CleanAreaDataBean.java`; sent from `com/ilife/home/robot/activity/BaseMapX9Activity.java` ~l.940 |
| Room clean (cross-check) | `com/aliyun/iot/aep/sdk/bean/CleanPartitionDataBean.java`, `BaseMapX9Activity.java` ~l.955 |
| No-go zones | `com/ilife/home/robot/view/helper/helperx9/ForbiddenAreaHelper.java` (`getFbdaData`, `setForbiddenArea`); type values in `view/MapView.java` l.167 and `view/MapViewX9.java` l.207 |
| Virtual walls | `com/ilife/home/robot/view/helper/helperx9/VirtualWallHelper.java` (`getVwData`, `setVirtualWall`) |
| Go-to point | `com/aliyun/iot/aep/sdk/bean/PointToGoBean.java`; `view/helper/helperx9/PointToGoHelper.java` l.152; `activity/PointToGoActivity.java` `pointToGoStart` |
| Coordinate frame | `com/ilife/home/robot/utils/DataUtils.java` `parseSaveMapData` (cells → `Coordinate(col + left, row - top)`), `intToBytes`/`bytesToInt` (BE s16); `view/MapViewX9.java` `matrixCoordinate*`/`reMatrixCoordinate*` |
| Do-not-disturb | `com/ilife/home/robot/activity/ActivityNoDisturb.java`; `IlifeAli.java` `BeepNoDisturb` |
| Saved maps | `com/aliyun/iot/aep/sdk/bean/SaveMapBean.java`; `IlifeAli.setSelectMapId` |
| Room doors | `com/ilife/home/robot/activity/SegmentationRoomX9Activity.java` l.700–740; `view/helper/helperx9/SegmentationRoomHelper.java` `getSegmentationData` |
| Room/map names | `com/ilife/home/robot/activity/RenameActivity.java` l.241–259 |
| Tuya standard sweeper frames (`command_trans`) | [tuya/tuya-panel-demo `examples/laserSweepRobot`](https://github.com/tuya/tuya-panel-demo/tree/main/examples/laserSweepRobot): `src/utils/index.tsx` `getCommonData`, `src/protocol/area/index.ts` |

GitHub code search for every DP code turned up nothing ILIFE- or Tuya-specific, apart from this repo
and tuya-local's `ilife_a30_pro_vacuum.yaml`, which maps none of these DPs. Web search found no Tuya
documentation for these vendor DPs.

## Common building blocks (verified from ILIFEHOME code)

### Points

```
s16 BE x, s16 BE y          4 bytes per point
```

- **Units: map cells** (one grid cell of the map, i.e. `resolution_cm`). `DataUtils.parseSaveMapData`
  builds every map cell as `Coordinate(col + leftX, row - topY)`, and the drawing helpers convert
  screen ↔ map only by scale and offset. No cm or mm factor is applied anywhere before
  `intToBytes(round(v))`.
- **Origin:** the robot's map origin, the same zero as the map header's origin.
- **Axis:** the app keeps screen-style y-down internally and writes `-y`, so **y points up** on the
  wire. `CleanAreaHelper`, `ForbiddenAreaHelper`, `VirtualWallHelper`, `PointToGoHelper` and
  `SegmentationRoomHelper` all negate odd indices on encode and decode.
- The integration independently found the A30 Pro map file's wall and zone records "in cells from
  the robot origin, y up" (`tuya_map.py` module docstring, `TestA30` in `tests/test_tuya_map.py`).
  That is the same convention, so the zone DPs almost certainly share that frame.

Conversion from the integration's map frame, with `units = resolution_cm * 2` and the header fields
from `tuya_map._parse_header`:

```
cell offset (DP)  ->  grid column/row (y down, as drawn)
col = origin_x / units + x
row = origin_y / units - y

grid column/row  ->  cell offset (DP)
x = col - origin_x / units
y = origin_y / units - row

robot units (path points)  ->  cell offset:  x_cell = x_units / units,  y_cell = y_units / units
```

### Rectangle / zone geometry

Four corners, 16 bytes. The app creates them in this order: `(left,top) (right,top) (right,bottom)
(left,bottom)` in screen terms, then negates y. Zones may be **rotated**: the app has a rotate handle
and sends the four transformed corners, not an axis-aligned box.

### Passes: the `CleanLoop` byte

`CleanAreaDataBean` / `CleanPartitionDataBean`:

```
getSettingTimes() = CleanLoop & 0x0F          passes requested (app sends 1 or 2)
getCleanedTimes() = (CleanLoop >> 4) & 0x0F   passes completed (robot echo)
```

This explains the integration's existing observation that the robot echoes `CleanPartitionData`
"with the pass in progress": the echo sets the high nibble.

### Starting the job

The ILIFEHOME app writes only the struct, with `Enable = 1` (`BaseMapX9Activity`, `PointToGoActivity`),
and sends no separate mode or start command. It stops by setting the work mode to wait
(`AliSkills.enterWaitMode`). This matches what the integration already sees on Tuya for
`CleanPartitionData`, where writing it starts the room clean. **Expect writing dp 139 or dp 141
alone to start the job.** Writing `mode`/`switch_go` afterwards should not be needed and could
override the job. This is unverified on the A30 Pro.

---

## dp 139 `CleanAreaData`: zone (rectangle) cleaning

**Aliyun original (verified):**

```json
{"CleanAreaData": {"Enable": 1, "CleanLoop": <passes>, "AreaData": "<base64 16 bytes>"}}
```

`AreaData` is one rectangle, 4 × (s16 x, s16 y), cells, y up. The empty value is 16 zero bytes,
`AAAAAAAAAAAAAAAAAAAAAA==`. The X9 app supports exactly one zone per job.

**Tuya A30 Pro (inferred, by analogy with dp 129):**

| off | len | field | notes |
|---|---|---|---|
| 0 | 1 | Enable | 1 = start; robot shows 0 when idle |
| 1 | 1 | CleanLoop | low nibble = passes (1–2); high nibble = passes done (echo) |
| 2 | 16·N | zones | per zone 4 points, each `s16 BE x, s16 BE y` (cells, y up) |

Confidence: **inferred**. The inner 16-byte zone is verified from code. The two-byte header and the
field order are inferred from `CleanPartitionData`, which flattens the same `{Enable, CleanLoop,
…}` struct to `01 <passes> <payload>`. Whether N > 1 is allowed is unknown. The X9 sends exactly one;
a 255-character base64 limit allows up to 11. **Alternative to rule out:** a zone-count byte after
CleanLoop (`01 pp NN …`).

Worked example: 2 passes over the box x ∈ [-20, 15], y ∈ [-10, 12] (cells):

```
corners  (-20, 12) (15, 12) (15, -10) (-20, -10)     # (left,top) (right,top) (right,bottom) (left,bottom)
bytes    01 02  ffec 000c  000f 000c  000f fff6  ffec fff6
base64   AQL/7AAMAA8ADAAP//b/7P/2
```

## dp 141 `CleanPointData`: spot / go-to-point

**Aliyun original (verified):** the property is `PointToGo`, not `CleanPointData`:

```json
{"PointToGo": {"Enable": 1, "PointData": "<base64 of s16 BE x, s16 BE y>"}}
```

`PointToGoHelper.getPointOfRobot()` returns `(round(x), -round(y))`, so the point is in cells with
y up. Writing it with `Enable = 1` starts the run.

**Tuya A30 Pro (inferred):**

| off | len | field |
|---|---|---|
| 0 | 1 | Enable (1 = go) |
| 1 | 1 | CleanLoop / passes? (*may be absent*) |
| 2 | 4 | `s16 BE x, s16 BE y` (cells, y up) |

Confidence: **guess** for the header, **verified** for the point encoding. The Tuya name
`CleanPointData` and the `mode` enum value `pose` suggest "go to the point and spot-clean". It may
therefore carry a passes byte like dp 139 (6 bytes in all) or be just `Enable + point` (5 bytes).
The status enum has `goto_pos`.

Example, spot at (5, -8), 1 pass, under the 6-byte hypothesis: `01 01 0005 fff8` → `AQEABf/4`.

## dp 142 `ForbidZoneData` and dp 147 `mop_forbiden_data`: no-go zones

**Aliyun original (verified):** a single property, `ForbiddenAreaData`, base64:

| off | len | field |
|---|---|---|
| 0 | 4 | type, u32 BE: **0 = no-go (sweep and mop), 1 = no-mop** |
| 4 | 16 | 4 points, `s16 BE x, s16 BE y` (cells, y up) |

That 20-byte record repeats once per zone. The X9 pads to 10 slots (200 bytes) and the other
families send `N × 20` bytes. A zone whose eight coordinates are all zero is skipped on decode.

**Tuya A30 Pro (inferred):** Tuya's 255-character string limit (191 raw bytes) cannot hold the
200-byte X9 form. That explains why the port split it into **dp 142 (no-go) and dp 147 (no-mop)**.
The most likely layout for each is

| off | len | field |
|---|---|---|
| 0 | 20·N | N × (u32 type, 4 points), type 0 in dp 142 and 1 in dp 147 |

or the same records without the 4-byte type (16·N). Confidence: **inferred**. The record body is
verified; whether the type word was kept, and whether there is padding, are unknown.

The A30 Pro *map file* stores no-go zones as tag `0x1B`, a u16 count, then 16 bytes of 4 points per
zone, with no type (`tuya_map._parse_records`). The DP may well mirror that, as `count + 16·N`.

Writing the DP saves the zones. It does not start a job.

Example, one no-go box (-3..2, 4..9), 20-byte form with type: `00000000 fffd0009 00020009 00020004
fffd0004` → `AAAAAP/9AAkAAgAJAAIABP/9AAQ=`.

## dp 140 `VirtualWallData`: virtual walls

**Aliyun original (verified):** base64. Each wall takes 12 bytes:

| off | len | field |
|---|---|---|
| 0 | 4 | reserved / type: the app writes 0 and ignores it on read |
| 4 | 4 | start point `s16 BE x, s16 BE y` |
| 8 | 4 | end point |

The X9 pads to 10 walls (120 bytes); the others send `N × 12`. An all-zero wall is skipped. On read
the app swaps the endpoints so that x1 ≤ x2.

**Tuya A30 Pro (inferred):** 120 bytes fits in 255 base64 characters, so the Aliyun payload probably
passes through unchanged. Possible variants are `N × 12` instead of padded, or the map-file form
(tag `0x13`, u8 count, then `N × 8`). Confidence: **inferred** (body verified).

Example, one wall from (-5, 3) to (7, 3), 12-byte form: `00000000 fffb0003 00070003` →
`AAAAAP/7AAMABwAD`.

## dp 146 `robot_position`: live position

There is no Aliyun counterpart in ILIFEHOME. The X9 family gets the robot position from the realtime
path stream. **Guess:** `s16 BE x, s16 BE y` in cells with y up, possibly followed by a heading
(s16, degrees). The integration's local-transport notes record that dp 146 was **not pushed**
during a local cleaning run, so the robot may only fill it on request, or only on the cloud channel.
Confidence: **guess**.

## dp 143 `setting_disturb`: do-not-disturb window

**Aliyun original (verified):** `BeepNoDisturb {Switch: 0/1, Time: u32}`. `Time` packs four bytes,
`[startHour, startMin, endHour, endMin]` (`ActivityNoDisturb`: `bArr[0..3]`).

**Tuya value** (the captured window is the owner's and is not reproduced; this example has
the same shape, for 23:00–07:00) `"0117000700"`: a plain ASCII string, not base64. Read as hex
bytes it is `01 17 00 07 00`, which is **flag 01, start 0x17:0x00 = 23:00, end 0x07:0x00 = 07:00**.
That is the same 4-byte Aliyun `Time` hex-encoded behind one leading byte. The captured value
read as a typical night-time DND window this way, and as an implausible one in decimal. dp 25
`switch_disturb` was `False` in the same capture, so the leading `01` is probably not the on/off
switch. It is more
likely a format or version byte, or "window valid". Confidence: **inferred** (hex reading).

Check it by setting DND to, for example, 23:30–07:15 in the app and reading dp 143. The hex reading
predicts `01171e070f`.

## dp 130 / 131 `AddRoomDoor` / `DeleteRoomDoor`: room split / door edit

**Aliyun original (verified):**

```json
{"AddRoomDoor":    {"ModifyResult": 0, "CmdId": <epoch s>, "MapId": <map id>, "ModifyInfo": "<b64 12 bytes>"}}
{"DeleteRoomDoor": {"ModifyResult": 0, "CmdId": <epoch s>, "MapId": <map id>, "ModifyInfo": <int door/room index>}}
```

`ModifyInfo` for an add is `u32 BE roomId` (the room being split) followed by the two endpoints of
the dividing line, `s16 x, s16 y` each (cells, y up). The robot answers with the same property,
setting `ModifyResult` (0 ok / else error). On Tuya both DPs read empty when idle. The flattening
order is unknown; the likeliest is `MapId u32, CmdId u32, ModifyInfo…, ModifyResult u8`.
Confidence: **guess** for the Tuya layout.

## dp 128 `SaveMap`: saved-map slots

**Aliyun original (verified):** `SaveMap {SelectedMapId: u32, SaveMapId: base64 of N × u32 BE}`.
The empty `SaveMapId` is 12 zero bytes, which means 3 slots.

**Tuya value** (ids made up here; the captured ones are the owner's) `agAAAWgAAAJqAAABAAAAAAAAAAAAAAAA` decodes
to 24 bytes:

```
6a000001 | 68000002 6a000001 00000000 00000000 00000000
selected | saved map ids (5 slots)
```

The captured map ids read as epoch seconds of map creation (both dated within the past year).
The selected id is also the first word of `CleanSettings` (dp 136). That first word is
the **map id**, not a timestamp as `tuya_rooms.py` currently describes it. Confidence:
**inferred** (strong).

## dp 144 `user_map_name`

The value is base64 and decodes to `&#*#&<name>`. This is Tuya-only, with no Aliyun counterpart.
**Guess:** map names joined with the separator `&#*#&`, which would make it an empty first entry
plus `<name>`, or a `<prefix>&#*#&<name>` pair. Renaming a map in the app and reading the DP back
answers it. Low priority.

---

## The `command_trans` (dp 15) route: Tuya standard sweeper frames

Frame (tuya-panel-demo `getCommonData`): `aa | 00 (version) | len (u8, bytes of cmd+data) | cmd |
data | checksum`. The checksum is the sum of cmd and data bytes, mod 256. Commands:

| cmd | meaning | data (V1.1.0) |
|---|---|---|
| 0x28 / 0x29 | zone clean set / report | `passes u8, zones u8`, then per zone `npoints u8` + points |
| 0x16 / 0x17 | go-to/spot set / report | one point |
| 0x12 / 0x13 | virtual walls set / report | `n u8`, then per wall 2 points |
| 0x1A / 0x1B | no-go set / report | `n u8`, then per zone `mode u8 (00 all, 01 sweep, 02 mop)`, `npoints u8`, points |

In the standard protocol the points are `s16 BE`, in **robot units relative to the map origin**,
with y negated.

What the A30 Pro emits matches these *report* opcodes with empty or near-empty payloads:

| frame | reading |
|---|---|
| `aa0002 13 00 13` | 0x13 walls, n = 0 |
| `aa0001 17 17` | 0x17 spot, none |
| `aa0004 29 000000 29` | 0x29 zone report, passes 0, zones 0, plus one byte |
| `aa0004 1b 000200 1d` | 0x1B no-go report: does not parse cleanly as V1.1.0. Maybe a u16 count of 2 with no geometry, or a different layout |

So the firmware implements at least the report side of the standard protocol. **Whether it accepts
0x28/0x16/0x1A writes is unverified**, and the ILIFE app evidently uses the vendor DPs instead.
Prefer dp 139/141/142 and keep `command_trans` as a fallback to test.

---

## Python reference (not wired into the integration)

```python
"""ILIFE A30 Pro zone DPs: verified inner payloads, inferred Tuya wrappers (see doc)."""
import base64
import struct

Point = tuple[int, int]          # map cells from the robot origin, y up


def _pts(points: list[Point]) -> bytes:
    return b"".join(struct.pack(">hh", x, y) for x, y in points)


def _unpts(raw: bytes) -> list[Point]:
    return [struct.unpack_from(">hh", raw, i) for i in range(0, len(raw) - 3, 4)]


def rect(x0: int, y0: int, x1: int, y1: int) -> list[Point]:
    """Axis-aligned box in the corner order the app uses: (left,top) (right,top) (right,bottom) (left,bottom)."""
    left, right, bottom, top = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


# dp 139: inferred wrapper [Enable][CleanLoop] + 16 bytes per zone
def encode_clean_area(zones: list[list[Point]], passes: int = 1) -> str:
    if not 1 <= passes <= 2 or not zones:
        raise ValueError("1-2 passes and at least one zone")
    body = b"".join(_pts(z) for z in zones)
    return base64.b64encode(bytes([1, passes & 0x0F]) + body).decode()


def decode_clean_area(value: str) -> dict:
    raw = base64.b64decode(value)
    if len(raw) < 2:
        return {"enable": 0, "passes": 0, "done": 0, "zones": []}
    zones = [_unpts(raw[i:i + 16]) for i in range(2, len(raw) - 15, 16)]
    return {"enable": raw[0], "passes": raw[1] & 0x0F, "done": raw[1] >> 4, "zones": zones}


# dp 141: inferred wrapper [Enable][CleanLoop] + point
def encode_clean_point(point: Point, passes: int = 1) -> str:
    return base64.b64encode(bytes([1, passes]) + _pts([point])).decode()


# dp 142 / 147: verified Aliyun record (type u32 + 4 points), wrapper inferred
FORBID_ALL, FORBID_MOP = 0, 1


def encode_forbid_zones(zones: list[list[Point]], kind: int = FORBID_ALL) -> str:
    return base64.b64encode(b"".join(struct.pack(">I", kind) + _pts(z) for z in zones)).decode()


def decode_forbid_zones(value: str) -> list[dict]:
    raw = base64.b64decode(value)
    out = []
    for i in range(0, len(raw) - 19, 20):
        pts = _unpts(raw[i + 4:i + 20])
        if any(c for p in pts for c in p):
            out.append({"type": struct.unpack_from(">I", raw, i)[0], "points": pts})
    return out


# dp 140: verified Aliyun record (4 reserved bytes + 2 points), wrapper inferred
def encode_virtual_walls(walls: list[tuple[Point, Point]]) -> str:
    return base64.b64encode(b"".join(b"\0\0\0\0" + _pts([a, b]) for a, b in walls)).decode()


def decode_virtual_walls(value: str) -> list[list[Point]]:
    raw = base64.b64decode(value)
    walls = [_unpts(raw[i + 4:i + 12]) for i in range(0, len(raw) - 11, 12)]
    return [w for w in walls if any(c for p in w for c in p)]


# dp 143: inferred hex-ASCII "<flag><sH><sM><eH><eM>"
def decode_disturb(value: str) -> dict:
    b = bytes.fromhex(value)
    return {"flag": b[0], "start": f"{b[1]:02d}:{b[2]:02d}", "end": f"{b[3]:02d}:{b[4]:02d}"}


def encode_disturb(start: tuple[int, int], end: tuple[int, int], flag: int = 1) -> str:
    return bytes([flag, *start, *end]).hex()


# grid <-> DP frame (header from tuya_map._parse_header)
def cell_to_grid(p: Point, header: dict) -> tuple[float, float]:
    u = header["resolution_cm"] * 2
    return header["origin_x"] / u + p[0], header["origin_y"] / u - p[1]


def grid_to_cell(col: float, row: float, header: dict) -> Point:
    u = header["resolution_cm"] * 2
    return round(col - header["origin_x"] / u), round(header["origin_y"] / u - row)


assert encode_clean_area([rect(-20, -10, 15, 12)], 2) == "AQL/7AAMAA8ADAAP//b/7P/2"
assert decode_disturb("0117000700") == {"flag": 1, "start": "23:00", "end": "07:00"}
```

## What would confirm each one (smallest live capture)

Read the shadow (`/v2.0/cloud/thing/{id}/shadow/properties`) or watch LAN dp pushes during each step.

1. **dp 139:** in the app, draw **one** zone, set passes = 2, start, and read dp 139 at once. Check
   the 2-byte header, the zone count and the units: the corner coordinates should be single- or
   double-digit cells, inside the map's `[-origin/units … width-origin/units]` range. Repeat with
   two zones if the app allows it.
2. **dp 141:** tap one spot and go. Read dp 141 for its length (5 vs 6 bytes) and the point.
3. **dp 142 / 147:** add one no-go zone and one no-mop zone. Read both DPs and check for the
   4-byte type and any padding. Then fetch the map file and compare against its tag `0x1B` record.
4. **dp 140:** add one wall and read dp 140 (12-byte vs 8-byte records, padded or not).
5. **dp 146:** read it while the robot is cleaning, through the cloud shadow rather than LAN.
6. **dp 143:** set DND to 23:30–07:15 and expect `01171e070f`.
7. **Start semantics:** after step 1, check that `status` goes to `zone_clean` with no `mode` or
   `switch_go` write.

## Verified vs not

| Item | Status |
|---|---|
| Point encoding (s16 BE, cells, y up, origin = map origin) | **verified** from ILIFEHOME code; consistent with the integration's A30 map-file findings |
| Zone = 4 corners (rotatable), 16 bytes | **verified** (ILIFE code) |
| Passes in the CleanLoop low nibble, done count in the high nibble | **verified** (ILIFE code); explains the dp 129 echo |
| Writing the area / point DP with Enable = 1 starts the job | **verified** for the ILIFE Aliyun app; **inferred** for the A30 Pro |
| No-go record = type (0 all / 1 mop) + 4 points; wall = 4 reserved bytes + 2 points | **verified** (ILIFE Aliyun) |
| Tuya wrappers for dp 139/140/141/142/147 (header bytes, counts, padding) | **inferred**, needs one capture each |
| dp 143 hex reading (flag, start hh:mm, end hh:mm) | **inferred** |
| dp 128 = selected id + 5 saved map ids; CleanSettings word 0 = map id | **inferred** (strong) |
| dp 130/131, 144, 146 Tuya layouts | **guess** |
| `command_trans` zone writes (0x28/0x16/0x1A) accepted | **unverified**; only report frames have been seen |

## Live verification (2026-10-18 01:42, local LAN write, robot on dock)

**dp 139 `CleanAreaData` — VERIFIED.** Layout: `u8 enable=01, u8 passes, u8 zone_count, then per zone 4 corners × (s16 BE x, s16 BE y)` in map cells (5 cm on this robot: header `resolution_cm=5`), origin = map header origin, y up.

- `AQEBAAIABQAMAAUADP/7AAL/+w==` = `01 01 01 | (2,5) (12,5) (12,-5) (2,-5)` → the robot answered within 0.4 s with `mode=zone`, `status=zone_clean`, `switch_go=true` and a `command_trans` frame `aa 00 14 29 17 01 04 …` (Tuya sweeper cmd 0x29 zone echo). Writing dp 139 alone starts the job; no `mode`/`switch_go` needed.
- The same payload **without** the zone-count byte (`01 01 | corners`, the Aliyun layout) was ignored.
- dp 139 does not appear in a later DP_QUERY (reads back `None`).

**dp 141 `CleanPointData` — NOT confirmed.** Local writes of `01|pt`, `01 01|pt`, `01 01 01|pt` (pt = (7,0)), alone and together with `mode=pose`, were all ignored (no dp change at all). Needs one app capture: set a go-to point in the app and read dp 141 (and any `command_trans` frame) at that moment.

**dp 143 `setting_disturb`** reads a string of hex digits locally, `01 | hh mm | hh mm` (start, end; value not reproduced, it is the owner's); leading byte unconfirmed (dp 25 `switch_disturb` was off at the same time).
