# Local LAN control for ILIFE Clean (Tuya) vacuums — design

Date: 2026-10-18. Target device: ILIFE A30 Pro (`5309qt4sjd4uz4qz`, Tuya protocol 3.3),
the owner's robot, Home Assistant 2026.6 on HAOS.

## Intent

The owner wants one complete robot-vacuum entity in Home Assistant — state, start/pause/
stop/dock/locate, suction, water, cleaning mode, schedules, rooms, map with the cleaning
route — that keeps working when the internet is down. Today the ILIFE Clean backend of
this integration does everything except the last part: every read and write goes through
Tuya's cloud OpenAPI. The robot speaks Tuya's local protocol on the LAN (verified
2026-10-18: status read, start, pause, resume, dock all work locally, and locally a plain
`mode=smart` + `switch_go=true` starts it, while the same command through the cloud is
ignored unless the map was requested first).

## Goals

1. A local transport for the ILIFE Clean backend: status is pushed by the robot over the
   LAN, commands go over the LAN; the cloud becomes the fallback, not the path.
2. Everything that is a datapoint works without internet once the integration has started
   at least once with internet: state, battery, fault, start/pause/resume/stop/dock/
   locate, suction, water, cleaning mode, program, efficiency, switches (DND, resume after
   charging, auto-empty, carpet boost, Y-mop), volume, consumables, schedules, room
   cleaning (room names are cached).
3. Native HA area cleaning: `VacuumEntityFeature.CLEAN_AREA` with the robot's rooms as
   segments, so `vacuum.clean_area` works with HA areas.
4. Zone and spot cleaning services, once their datapoint formats are known (separate RE
   track: `docs/re/a30pro-zone-formats.md`).
5. The robot's changing DHCP address must not break local control (it has
   already changed once): find it by its device id on the LAN.

## Non-goals

- Map and route without internet. The robot uploads maps to Tuya's cloud; nothing map-like
  was seen on the LAN (dp 146 `robot_position` was not pushed during a local run). The map
  camera and the per-clean route keep coming from the cloud and show the last known map
  while offline.
- The ILIFEHOME (Alibaba) backend — untouched.
- A rewrite of the cloud client or the card.

## Anti-goals

- The cloud path must keep working exactly as today when local is off or unreachable —
  existing users of the upstream integration must not notice anything unless they enable
  local control.
- No secret (local key) in logs or diagnostics.
- No new hard dependency that Home Assistant has to compile; pure Python + the
  `cryptography` package HA already ships.

## Design

### `tuya_local.py` — protocol client (pure asyncio, no HA imports)

Tuya local protocol 3.3 (55AA frames, CRC32, AES-128-ECB with the 16-byte local key, the
3.3 version header on everything but DP_QUERY). One persistent TCP connection to port
6668: DP_QUERY (0x0a) on connect, CONTROL (0x07) to write `{dps: {id: value}}`, STATUS
(0x08) pushes decoded into `{dp_id(str): value}` callbacks, HEART_BEAT (0x09) every 10 s,
reconnect with back-off. Also a UDP listener on 6666/6667 that decodes discovery
broadcasts (3.3: AES-ECB with md5("yGAdlopoPVldABfn")) to learn the robot's IP from its
`gwId`. Unit-tested with frames captured from the real robot.

### Code ↔ dp id mapping

The coordinator speaks codes. Two vocabularies exist for the same dp: the thing model's
(`switch_go`, `residual_electricity`, `clean_area_total`...) and the standard instruction
set the REST status uses and the integration's constants follow (`power_go`,
`electricity_left`, `total_clean_area`...). Mapping = thing-model `abilityId` → code, then
a small alias table rewrites the model codes the constants know under their standard names.
The model is fetched from the cloud at first start and cached (HA `Store`), together with
the local key (from `/v1.0/devices/{id}` `local_key`), the last good IP, the device list
entry, the `/specifications` response and the last product properties (room names,
CleanSettings). Entities derive their features from the specification, so without this
cache a restart while the internet is down would set up a vacuum with no features at all.
On startup the integration uses the cache when the cloud is unreachable and refreshes it
when the cloud answers.

### Coordinator (hybrid)

`ILifeTuyaCoordinator` gains an optional local link. When connected:
- status and product properties come from local pushes (`async_set_updated_data`), the
  REST status poll stops; properties (rooms, schedules, CleanSettings) are read from the
  same local dps;
- `async_write` and the vacuum's command paths send locally; a local send failure falls
  back to the cloud path;
- cloud keeps: first-run model/key fetch, map, realtime map, cleaning history (unchanged
  cadence), room-name refresh.
When the link is down the coordinator behaves exactly as today.

`online` = local link up OR cloud says online.

### Commands

Local start = `{pause:false, mode:smart, switch_go:true}` (verified). Pause = `pause:true`;
the robot answers by dropping `switch_go`, reporting `standby` and clearing `pause` at
once, so "paused" is tracked by the entity until the status moves away from `standby`
(resume = `pause:false`, verified). Dock = `switch_charge:true` (verified locally).
Cloud start keeps today's command (verified 2026-10-18 through this integration's
OpenAPI path; only HA's own Tuya integration needed a map request first).

### Vacuum entity

Adds `CLEAN_AREA`: `async_get_segments()` returns the rooms (`room id` → name), and
`async_clean_segments(segment_ids)` writes CleanPartitionData (existing encoder).
Existing `ilife.clean_rooms`, schedule services, program select stay.

### Config

New options step for ILIFE Clean entries: "Local control" (on by default for new and
existing entries once a local key is available), optional fixed host. Diagnostics show
local link state, host, protocol, last push age — never the key.

## Verification

- Unit tests: frame encode/decode/CRC against captured frames; discovery decode; mapping
  incl. aliases; pause tracking state machine; segments.
- Live, on the owner's robot (volume 0, short runs, owner permitted): local start → pause
  → resume → dock; suction/water writes; status push latency; cloud blocked (HA firewall
  rule or wrong cloud host) → everything datapoint-based still works; IP change handled
  (simulated by a wrong configured host + discovery).

## Left to the builder

Reconnect timings, exact Store layout, entity naming of new pieces, whether discovery runs
continuously or only when the link is down.
