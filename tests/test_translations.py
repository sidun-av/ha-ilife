"""strings.json and every translation carry the same keys, and the select/fan-speed
state translations cover every value the A30 Pro thing model can report. Pure."""
from __future__ import annotations

import json
import pathlib
import re

import pytest

_PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
FILES = [_PKG / "strings.json", *sorted((_PKG / "translations").glob("*.json"))]
# hassfest's translation key pattern (script/hassfest/translations.py).
_TRANSLATION_KEY = re.compile(r"^(?!.+[_-]{2})(?![_-])[a-z0-9-_]+(?<![_-])$")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _keys(node, prefix=""):
    if not isinstance(node, dict):
        return {prefix}
    out = set()
    for key, value in node.items():
        out |= _keys(value, f"{prefix}/{key}")
    return out


def test_languages_present():
    assert {p.stem for p in FILES} >= {"strings", "en", "fr", "ru"}


@pytest.mark.parametrize("path", FILES[1:], ids=lambda p: p.name)
def test_same_keys_as_strings(path):
    reference = _keys(_load(FILES[0]))
    keys = _keys(_load(path))
    assert keys - reference == set(), "keys missing from strings.json"
    assert reference - keys == set(), "keys missing from this translation"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_empty_values(path):
    def walk(node, where):
        for key, value in node.items():
            if isinstance(value, dict):
                walk(value, f"{where}/{key}")
            else:
                assert isinstance(value, str) and value.strip(), f"{where}/{key}"
    walk(_load(path), "")


def test_state_keys_are_valid_translation_keys():
    # hassfest's own rule: lowercase, digits, "-" and "_", neither at either end nor
    # doubled. An option like "S-shape" can't have a key.
    for key in _keys(_load(FILES[0])):
        if "/state/" in key:
            assert _TRANSLATION_KEY.fullmatch(key.rsplit("/", 1)[1]), key


def test_translation_key_rule_matches_hassfest():
    for good in ("strong", "goto_pos", "s-shape", "a1"):
        assert _TRANSLATION_KEY.fullmatch(good), good
    for bad in ("_x", "x_", "a__b", "a-_b", "-x", "Strong", "a b"):
        assert not _TRANSLATION_KEY.fullmatch(bad), bad


def _model_range(code):
    model = _load(_FIXTURES / "a30pro_model.json")
    for service in model["services"]:
        for prop in service["properties"]:
            if prop["code"] == code:
                return prop["typeSpec"]["range"]
    raise KeyError(code)


@pytest.mark.parametrize(("code", "path"), [
    ("cistern", ("select", "water_level")),
    ("mode", ("select", "cleaning_mode")),
    ("cleaning_efficiency", ("select", "cleaning_efficiency")),
    ("direction_control", ("select", "direction_control")),
    ("request", ("select", "request")),
    ("suction", ("vacuum", "vacuum", "state_attributes", "fan_speed")),
])
def test_every_model_value_has_a_state(code, path):
    node = _load(FILES[0])["entity"]
    for part in path:
        node = node[part]
    assert set(_model_range(code)) <= set(node["state"])


def test_program_states_match_the_select_options():
    node = _load(FILES[0])["entity"]["select"]["cleaning_program"]["state"]
    assert set(node) == {"standard", "plan_1", "plan_2"}
