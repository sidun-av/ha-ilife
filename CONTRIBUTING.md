# Contributing

## Tests

There are two tiers. Both run offline: no robot, no Tuya account and no secrets
are needed, the fixtures in `tests/fixtures` stand in for them.

### Pure tests (no Home Assistant)

The protocol, map, command and cache logic lives in modules with no Home Assistant
imports, and `tests/` loads them straight from their files:

```bash
python -m venv .venv && . .venv/bin/activate
pip install pytest pytest-asyncio pillow cryptography
python -m pytest -q tests
```

`tests/ha` is skipped in this venv (it reports as one skipped module).

### Home Assistant tier (`tests/ha`)

The glue that only shows up inside Home Assistant: setup and its fallbacks without
the cloud (expired trial, cloud down), entity availability with the LAN link up or
gone, the vacuum's commands per model, the suction nudge, commands whose LAN
acknowledgement was lost, translated names, and the map camera's save timer. The
Tuya cloud is a fake client answering from the fixtures and the LAN link a fake
robot (`tests/ha/harness.py`).

It needs Python 3.13 and a Home Assistant install, so use a separate venv:

```bash
python3.13 -m venv .venv-ha && . .venv-ha/bin/activate
pip install -r requirements_test_ha.txt
python -m pytest -q tests/ha
```

Run it as its own directory: `tests/ha/pytest.ini` sets the asyncio mode and the
import path Home Assistant's test plugin needs, and only applies when `tests/ha`
is the path given to pytest.

## Privacy

This is a public repository. Never commit IP addresses, device ids, local keys,
Tuya credentials or anything from a real home (room names, maps, diagnostics).
Test ids and keys are made up; product ids (a model's public id, such as the
A30 Pro's in `const.py`) are fine.
