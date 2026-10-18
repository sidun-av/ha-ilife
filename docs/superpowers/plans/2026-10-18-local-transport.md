# Local LAN control for ILIFE Clean — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The ILIFE Clean backend talks to the robot over the LAN (Tuya protocol 3.3), uses the cloud only as fallback and for maps/history, survives restarts without internet, and exposes native HA area cleaning.

**Architecture:** A pure-asyncio `tuya_local.py` (codec, connection, discovery) with no HA imports; a pure `tuya_dpmap.py` (dp id ↔ code); a `tuya_cache.py` wrapper over HA `Store`; the existing `ILifeTuyaCoordinator` gets an optional local link and a single `async_send(commands)` path that the vacuum entity uses for every command.

**Tech Stack:** Python 3.13, Home Assistant 2026.6 custom integration, `cryptography` (AES-ECB; already in HA core), pytest (+ pytest-asyncio for the connection tests).

**Spec:** `docs/superpowers/specs/2026-10-18-local-transport-design.md`

## Global Constraints

- No new entries in `manifest.json` `requirements`; only stdlib + `cryptography`.
- The local key never appears in logs, exceptions, diagnostics or test fixtures (tests use the fake key `0123456789abcdef`).
- With local control off or unreachable, behaviour is identical to v0.7.1 (all existing tests keep passing unchanged).
- Tuya protocol 3.3 only; other versions → link refuses to start, logs once, cloud path continues.
- Tests stay HA-free like the existing ones (load modules by path, see `tests/test_tuya_api.py` header); HA-dependent glue is verified live (Task 8).
- CI (`.github/workflows/*.yml`) installs `pytest pillow`; add `cryptography pytest-asyncio`.
- Device under test: id `<device-id>`, product `5309qt4sjd4uz4qz`, LAN host `<robot-ip>`.

## Review Focus

1. Robot reboots / Wi-Fi drops mid-session → link reconnects on its own, entities stay available via cloud meanwhile, no log spam (one warning per outage). Test: Task 2 `test_reconnects_after_server_closes`.
2. Two frames arrive in one TCP read, or one frame split across reads → both decoded, nothing lost. Test: Task 1 `test_stream_decoder_handles_split_and_joined_frames`.
3. HA restarts with internet down → vacuum still has start/pause/dock/fan speed (features from cached spec). Test: Task 4 `test_cached_spec_is_used_when_cloud_fails` (pure helper) + live check in Task 8.
4. Robot answers a pause by reporting `standby` with `pause` cleared → entity shows `paused`, next Start resumes instead of restarting. Test: Task 6 `test_pause_then_standby_is_paused_until_status_moves`.
5. A dp the thing model doesn't know (e.g. 132 `AppRemind` value types, unknown ids) arrives locally → ignored, never crashes the push handler. Test: Task 3 `test_unknown_dp_ids_are_dropped`.

---

### Task 1: Protocol 3.3 codec

**Files:**
- Create: `custom_components/ilife/tuya_local.py` (codec part)
- Test: `tests/test_tuya_local_codec.py`

**Interfaces:**
- Produces:
  - `CMD_CONTROL = 0x07`, `CMD_STATUS = 0x08`, `CMD_HEART_BEAT = 0x09`, `CMD_DP_QUERY = 0x0A`, `UDP_KEY = md5(b"yGAdlopoPVldABfn").digest()`
  - `pack_message(seqno: int, cmd: int, payload: dict | None, key: bytes) -> bytes` — JSON payload (`separators=(",", ":")`), AES-128-ECB PKCS7 with `key`; for every cmd except `CMD_DP_QUERY` and `CMD_HEART_BEAT` prefix the ciphertext with `b"3.3" + 12 zero bytes`; frame = `000055aa` seq(4) cmd(4) len(4) body crc32(4) `0000aa55`, len counts body+crc+suffix.
  - `class StreamDecoder: feed(data: bytes) -> list[tuple[int, int, dict | None]]` — yields `(seqno, cmd, payload)`; strips the 4-byte return code on device→client frames, the optional `3.3`+12 header, decrypts, parses JSON; empty body → `None`; bad CRC → frame dropped (logged at debug).
  - `decode_discovery(packet: bytes) -> dict` — decrypt with `UDP_KEY`, return the JSON (`gwId`, `ip`, `version`, `productKey`).

- [ ] **Step 1: Write failing tests**: `test_pack_control_matches_reference` (bytes produced by tinytuya 1.20.0 `pack_message` for seq 1, CONTROL, `{"devId":"<device-id>","uid":"<device-id>","t":"1760000000","dps":{"1":true}}`, key `0123456789abcdef` — generate the expected hex once with tinytuya in a scratch venv and paste it as a literal); `test_round_trip_status_frame` (a device-style STATUS frame with return code 0, `3.3` header, payload `{"dps":{"5":"smart"},"t":1}` decodes to `(seq, 8, {...})`); `test_stream_decoder_handles_split_and_joined_frames` (two frames concatenated, fed in 3 arbitrary chunks → 2 results in order); `test_bad_crc_is_dropped`; `test_decode_discovery_fixture` (`tests/fixtures/tuya_discovery_33.bin` → `gwId == "<device-id>"`, `ip == "<robot-ip>"`, `version == "3.3"`).
- [ ] **Step 2:** Run `python -m pytest tests/test_tuya_local_codec.py -q` → FAIL (module missing).
- [ ] **Step 3:** Implement the codec in `tuya_local.py` (use `cryptography.hazmat.primitives.ciphers` AES/ECB + `padding.PKCS7(128)`; `binascii.crc32`).
- [ ] **Step 4:** Run the test file → PASS; run the whole suite → all pass.
- [ ] **Step 5:** Add `cryptography pytest-asyncio` to the CI pip line. Commit `feat(local): Tuya 3.3 frame codec and discovery decoder`.

### Task 2: Local connection

**Files:**
- Modify: `custom_components/ilife/tuya_local.py` (connection part)
- Test: `tests/test_tuya_local_link.py`

**Interfaces:**
- Consumes: Task 1 codec.
- Produces: `class TuyaLocalLink:`
  - `__init__(self, device_id: str, local_key: str, host: str, on_dps: Callable[[dict[str, Any]], None], on_state: Callable[[bool], None], port: int = 6668)`
  - `async start() -> None` (spawns the run loop task; returns immediately), `async stop() -> None`
  - `connected: bool`, `host: str` (settable; takes effect on next reconnect), `last_push: float | None` (monotonic)
  - `async set_dps(dps: dict[str, Any]) -> None` — raises `TuyaLocalError` when not connected or no ack within 5 s
  - `class TuyaLocalError(Exception)`
  - Behaviour: on connect send DP_QUERY, deliver its `dps` via `on_dps`; every STATUS push → `on_dps(payload["dps"])`; heartbeat every 10 s, connection considered dead after 25 s of silence; reconnect back-off 1, 2, 5, 10, 30 s (cap); `on_state(True/False)` only on transitions; one WARNING per outage, DEBUG otherwise.

- [ ] **Step 1: Failing tests** with an in-process `asyncio.start_server` fake device that speaks the codec: `test_query_on_connect_delivers_dps`, `test_push_is_delivered`, `test_set_dps_sends_control_frame` (server asserts it got CONTROL with `{"dps":{"2":true}}`), `test_reconnects_after_server_closes` (server closes the socket; link reports False then True and re-queries), `test_set_dps_when_disconnected_raises`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `TuyaLocalLink` (asyncio streams, one reader task, a `seqno` counter, futures keyed by seqno for acks — the robot acks CONTROL with an empty-payload frame carrying the same seqno).
- [ ] **Step 4:** Tests PASS; full suite PASS.
- [ ] **Step 5:** Live smoke (no robot movement): a throwaway script that starts the link against `<robot-ip>` with the real key from a key file outside the repo, prints the first `on_dps` keys and sets dp 26 to its current value. Expected: dps include `"5"` and `"8"`. Commit `feat(local): persistent local link with push, heartbeat and reconnect`.

### Task 3: dp id ↔ code mapping

**Files:**
- Create: `custom_components/ilife/tuya_dpmap.py`
- Test: `tests/test_tuya_dpmap.py`

**Interfaces:**
- Produces:
  - `MODEL_TO_STANDARD = {"switch_go": "power_go", "residual_electricity": "electricity_left", "clean_area_total": "total_clean_area", "clean_count_total": "total_clean_count", "clean_time_total": "total_clean_time"}`
  - `class DpMap: from_model(raw_model: dict) -> DpMap` (raw = the parsed `/v2.0/cloud/thing/{id}/model` `model` JSON with `services[].properties[].abilityId/code`), `code_for(dp_id: str) -> str | None` (standard name if aliased), `dp_for(code: str) -> str | None` (accepts both names), `to_dict()/from_dict()` for the cache.
  - `split_local_dps(dps: dict[str, Any], dpmap: DpMap) -> dict[str, Any]` → `{code: value}` for known ids only.
- Note: `TuyaClient.device_model()` today flattens the model and drops `abilityId`; add `TuyaClient.device_model_raw(device_id) -> dict` returning the parsed model JSON, and keep `device_model()` built on top of it.

- [ ] **Step 1: Failing tests** using a fixture `tests/fixtures/a30pro_model.json` (copy the real model JSON — it holds no secrets; fetch it with the project keys from a key file outside the repo, see `docs/re/a30pro-dp-map.md`): `test_standard_codes_are_aliased` (`code_for("1") == "power_go"`, `code_for("8") == "electricity_left"`, `dp_for("power_go") == dp_for("switch_go") == "1"`), `test_product_codes_map` (`code_for("129") == "CleanPartitionData"`, `code_for("120") == "Schedule1"`), `test_unknown_dp_ids_are_dropped` (`split_local_dps({"999": 1, "5": "smart"}, m) == {"status": "smart"}`), `test_round_trip_dict`.
- [ ] **Step 2–4:** red → implement → green (+ `device_model_raw` with a test in `tests/test_tuya_api.py` style using the fake `_do`).
- [ ] **Step 5:** Commit `feat(local): dp id/code mapping from the thing model`.

### Task 4: Offline cache

**Files:**
- Create: `custom_components/ilife/tuya_cache.py`
- Modify: `custom_components/ilife/__init__.py` (`_async_setup_ilife_clean_entry`, coordinator first refresh)
- Test: `tests/test_tuya_cache.py` (pure helpers only)

**Interfaces:**
- Produces:
  - `merge_cache(old: dict, **fresh) -> dict` — pure; keeps old values for keys whose fresh value is `None`.
  - `class DeviceCache:` wraps `homeassistant.helpers.storage.Store(hass, 1, f"ilife.{entry_id}")`; `async load() -> dict`, `async save(data: dict)`; layout `{device_id: {"device": {...list_devices entry...}, "spec": {...}, "model_raw": {...}, "properties": {...}, "local_key": str, "host": str}}`.
  - Setup: try `client.list_devices()`; on `TuyaError` (not auth) fall back to cached devices; per device fetch `device_detail` once for `local_key`/`ip`-less detail (`local_key` only) and save. Coordinator `_async_update_data` first-load path: on spec/model failure use cached ones; on success save them.
- [ ] Tests: `test_merge_keeps_old_when_fresh_is_none`, `test_cached_spec_is_used_when_cloud_fails` (pure function `pick(fresh, cached)` used by the coordinator).
- [ ] Commit `feat(local): cache device, spec, model, properties and local key for offline restarts`.

### Task 5: Hybrid coordinator

**Files:**
- Modify: `custom_components/ilife/__init__.py` (`ILifeTuyaCoordinator`)
- Test: `tests/test_tuya_local_apply.py` (pure helper)

**Interfaces:**
- Consumes: `TuyaLocalLink`, `DpMap`, `split_local_dps`, `DeviceCache`.
- Produces on `ILifeTuyaCoordinator`:
  - `local: TuyaLocalLink | None`, `local_connected: bool` (property)
  - `async async_send(commands: list[dict]) -> None` — `[{code, value}]`; when local is connected map codes via `DpMap.dp_for` and `set_dps` all at once; any unmapped code or `TuyaLocalError` → cloud (`api.send_many`, then `issue_properties` for codes outside the spec, as `async_write` does today). Then `async_request_refresh()` only on the cloud path.
  - `async_write(code, value)` becomes `await self.async_send([{"code": code, "value": value}])` plus today's optimistic `properties[code] = value` for product dps.
  - Pure helper `apply_local_dps(status: dict, properties: dict, update: dict[str, Any], model_codes: set[str]) -> tuple[dict, dict]` — standard codes go to `status`, product codes (those in `model_codes` and not in the standard alias targets / spec functions) also go to `properties`; returns new dicts.
  - Local push handler → `apply_local_dps` → re-parse room names when a `MapRoomInfo*`/`map_room_info_*` code changed → `async_set_updated_data(status)`; `_watch_run_end(status)` too.
  - While `local_connected`: `update_interval` becomes 300 s and `_async_update_data` skips `detail()` (keeps history/properties cloud refresh, failures there never mark the entity unavailable); when it drops back: 30 s and today's behaviour.
  - `online` = `local_connected or detail online`.
  - Link start: in setup after first refresh, if the entry option `local` (default True) and a cached `local_key` exist; host = option `host` or cached host or discovery (`tuya_local.discover(device_id, timeout=10)` — add this async helper in `tuya_local.py`: listens UDP 6666/6667, returns the IP for the given `gwId`, `None` on timeout; save found host to cache). On every reconnect failure streak ≥ 3 run discovery again and update `link.host` if it changed.
  - Unload: `await link.stop()`.
- [ ] Tests (pure): `test_apply_routes_standard_and_product_codes`, `test_apply_does_not_mutate_inputs`.
- [ ] Live: deploy to HA (see Task 8 deploy command), confirm in logs `local link connected` and that `vacuum.ilife_a30_pro_2` state changes within 2 s of a local change (set suction from the HA UI service → robot dp 9 → state).
- [ ] Commit `feat(local): coordinator prefers the LAN, cloud as fallback`.

### Task 6: Vacuum entity on the shared send path, pause tracking, area cleaning

**Files:**
- Modify: `custom_components/ilife/vacuum.py` (`TuyaVacuum`)
- Create: `custom_components/ilife/tuya_pause.py` (pure state machine)
- Test: `tests/test_tuya_pause.py`, `tests/test_tuya_segments.py`

**Interfaces:**
- Consumes: `coordinator.async_send`.
- Produces:
  - `TuyaVacuum._send_many` calls `coordinator.async_send(commands)` (same error mapping as today).
  - `class PauseTracker: paused_by_us(self) -> bool; on_pause_sent(); on_command_sent(); on_status(status: str | None, power_go: bool | None)` — after `on_pause_sent`, a status of `standby` (or `paused`) means paused; any status other than `standby`/`paused`/the cleaning statuses, or `on_command_sent()`, clears it.
  - `activity` returns PAUSED when `tracker.paused_by_us()` and status is `standby`; `_is_paused` uses it so Start sends `_cmd_resume`.
  - `CLEAN_AREA`: set the feature when `coordinator.supports_room_clean`; `async_get_segments() -> list[Segment]` (`Segment(id=str(room_id), name=name)` from `coordinator.room_names`); `async_clean_segments(segment_ids: list[str], **kwargs)` → `async_clean_rooms([int(i) for i in segment_ids])`. Import `Segment` from `homeassistant.components.vacuum` (exists in 2026.6).
- [ ] Tests: `test_pause_then_standby_is_paused_until_status_moves` (pause sent → status `smart` → `standby` ⇒ paused; then `goto_charge` ⇒ not paused), `test_start_clears_pause`, `test_segments_from_room_names` (pure function `segments_from_rooms({4: "Office", 0: "Living"}) == [("0","Living"),("4","Office")]` sorted by id).
- [ ] Live (owner permitted short runs, volume already 0): via HA services on `vacuum.ilife_a30_pro_2`: start → pause (state `paused`) → start (resumes: robot status back to `smart` without a new run) → return_to_base. Robot moves < 20 s.
- [ ] Commit `feat: local commands, pause tracking and native area cleaning`.

### Task 7: Options flow and diagnostics

**Files:**
- Modify: `custom_components/ilife/config_flow.py`, `custom_components/ilife/diagnostics.py`, `custom_components/ilife/strings.json`, `custom_components/ilife/translations/*.json`
- Test: none HA-free beyond existing; verify live.

**Interfaces:**
- Options flow for `backend == ilife_clean`: `local` (bool, default True), `host` (str, optional, empty = auto). Changing options reloads the entry.
- Diagnostics add per device: `local: {"enabled", "connected", "host", "protocol": "3.3", "last_push_age_s"}` — no key.
- [ ] Live: open options via `POST /api/config/config_entries/options/flow {"handler": <entry_id>}`, submit `{local: true, host: ""}` → `create_entry`; download diagnostics → contains `connected: true`, does not contain the local key string (grep).
- [ ] Commit `feat: local control options and diagnostics`.

### Task 8: Deploy and end-to-end verification

**Files:** `README.md` (new section "Local control"), `manifest.json` (`version` → `0.8.0-local.1`, `iot_class` → `local_push`).

- [ ] Deploy: copy `custom_components/ilife` into HA's `config/custom_components` (keep the previous copy as `ilife.prev`) and restart HA core. Rollback = swap `ilife.prev` back.
- [ ] Offline test: block the cloud for HA only — `docker exec homeassistant` can't edit iptables; instead set option `host` correctly and temporarily point Tuya cloud hosts to 127.0.0.1 via HA container `/etc/hosts` (restore after). Restart core. Expected: vacuum entity available with all features, start/dock work locally, map camera shows last image, logs show cloud errors at debug/warning only.
- [ ] IP change test: set option `host` to `192.0.2.250` → link fails 3× → discovery finds the robot → connected; option left empty afterwards.
- [ ] Commit, push branch to `origin` (the owner's fork).

### Task 9: Zone cleaning service and map calibration (added 2026-10-18 after dp 139 was verified live)

**Files:**
- Create: `custom_components/ilife/tuya_zones.py` (pure encoder)
- Modify: `custom_components/ilife/vacuum.py` (service `ilife.clean_zone`), `custom_components/ilife/__init__.py` or `services.yaml`/`strings.json` (service registration, as `clean_rooms` is done), `custom_components/ilife/camera.py` (calibration attribute)
- Test: `tests/test_tuya_zones.py`, `tests/test_tuya_calibration.py`

**Interfaces:**
- `CLEAN_ZONE_CODE = "CleanAreaData"`; `clean_zone_value(zones: list[tuple[int, int, int, int]], passes: int = 1) -> str` — each zone `(x1, y1, x2, y2)` in map cells (robot frame, y up), normalised to min/max, encoded as base64 of `01, passes, len(zones)` then per zone 4 corners `(x1,y2) (x2,y2) (x2,y1) (x1,y1)` as BE s16 — verified layout in `docs/re/a30pro-zone-formats.md` ("Live verification"). Raise `ValueError` for 0 zones, > 5 zones, passes ∉ {1,2}, or a coordinate outside s16.
- Service `ilife.clean_zone` on the vacuum: fields `zone` (list of `[x1, y1, x2, y2]` lists, required) and `repeats` (1–2, default 1) — the field names the xiaomi-vacuum-map-card's custom service call uses (`zone`, `repeats`). Writes via `coordinator.async_write(CLEAN_ZONE_CODE, value)`.
- `calibration_points(header: dict, scale: int) -> list[dict]` in `tuya_map.py`: three `{"vacuum": {"x": cx, "y": cy}, "map": {"x": px, "y": py}}` points for cells (0,0), (10,0), (0,10), with `px = (origin_x / units + cx) * scale`, `py = (origin_y / units - cy) * scale`, `units = resolution_cm * 2` (image is the full grid, `scale` as passed to `render_tuya_map_png` after its clamp — return the clamped scale in the render metadata). Camera exposes it as attribute `calibration_points`.
- Tests: `test_zone_value_matches_live_capture` (`clean_zone_value([(2, -5, 12, 5)], 1) == "AQEBAAIABQAMAAUADP/7AAL/+w=="` — corner order (x1,y2),(x2,y2),(x2,y1),(x1,y1) reproduces the live payload), `test_zone_bounds`, `test_calibration_points_on_a30_header` (header from `tests/fixtures` A30 map: origin 850/610, resolution 5, scale 6 → cell (0,0) ↦ pixel (510, 366)).
- Live (short movement, volume 0): call `ilife.clean_zone` with `[[2,-5,12,5]]` → robot reports `zone_clean`; `return_to_base` right after.
- Commit `feat: zone cleaning service and map calibration`.

### Task 10: Dashboard card

Not code in this repo: install `xiaomi-vacuum-map-card` (HACS frontend, or the release JS as a `www/` resource) on the owner's HA and add a dashboard view "Робот-пылесос" with: the map card (camera `camera.ilife_a30_pro_map`, `calibration_source: {camera: true}`, rooms as predefined selections from the vacuum's `rooms` attribute → `ilife.clean_rooms`, zone mode → `ilife.clean_zone`), plus the bundled ILIFE card for schedules/history. Verify it renders (screenshot via Playwright against HA with the token).
