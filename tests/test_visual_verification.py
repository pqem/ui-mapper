"""Verification parser + soft-mismatch confidence tests."""

from __future__ import annotations

from ui_mapper.visual.verification import (
    DialogOpenCheck,
    MenuOpenCheck,
    parse_dialog_open_response,
    parse_menu_open_response,
    verify_dialog_open,
    verify_menu_open,
)


# -- parsing ---------------------------------------------------------------

def test_parse_menu_open_valid():
    r = parse_menu_open_response(
        '{"menu_open": true, "menu_name": "File", "confidence": 0.9}'
    )
    assert r.is_open is True
    assert r.menu_name == "File"
    assert r.confidence == 0.9


def test_parse_menu_open_with_fences():
    r = parse_menu_open_response(
        '```json\n{"menu_open": false, "menu_name": "", "confidence": 0.2}\n```'
    )
    assert r.is_open is False
    assert r.confidence == 0.2


def test_parse_menu_open_invalid_json_degrades_safely():
    r = parse_menu_open_response("not even close to JSON")
    assert r.is_open is False
    assert r.confidence == 0.0


def test_parse_menu_open_clips_confidence():
    r = parse_menu_open_response('{"menu_open": true, "confidence": 2.5}')
    assert r.confidence == 1.0
    r = parse_menu_open_response('{"menu_open": true, "confidence": -0.5}')
    assert r.confidence == 0.0


def test_parse_dialog_open_valid():
    r = parse_dialog_open_response(
        '{"dialog_open": true, "title": "Export", "confidence": 0.85}'
    )
    assert r.is_open is True
    assert r.title == "Export"


# -- verify_menu_open soft mismatch ----------------------------------------

class _FakeProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None

    def query_vision(self, prompt: str, image: bytes) -> str:
        self.last_prompt = prompt
        return self.response


def test_verify_menu_open_mismatch_downgrades_confidence():
    # VLM says "Edit" is open but we expected "File" → confidence halved
    provider = _FakeProvider(
        '{"menu_open": true, "menu_name": "Edit", "confidence": 0.9}'
    )
    check = verify_menu_open(provider, image=b"fake", expected_name="File")
    assert check.is_open is True
    assert check.menu_name == "Edit"
    assert check.confidence == 0.45


def test_verify_menu_open_matching_name_keeps_confidence():
    provider = _FakeProvider(
        '{"menu_open": true, "menu_name": "File", "confidence": 0.8}'
    )
    check = verify_menu_open(provider, image=b"fake", expected_name="File")
    assert check.confidence == 0.8


def test_verify_menu_open_provider_error_returns_not_open():
    class Boom:
        def query_vision(self, prompt, image):
            raise RuntimeError("provider down")
    check = verify_menu_open(Boom(), image=b"fake", expected_name="File")
    assert check.is_open is False
    assert check.confidence == 0.0


def test_verify_dialog_open_basic():
    provider = _FakeProvider(
        '{"dialog_open": true, "title": "Preferences", "confidence": 0.9}'
    )
    check = verify_dialog_open(provider, image=b"fake")
    assert check.is_open is True
    assert check.title == "Preferences"
