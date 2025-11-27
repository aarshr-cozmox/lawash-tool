import os
import sys

import json
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app


@pytest.fixture(scope="module")
def client():
    app.testing = True
    with app.test_client() as test_client:
        yield test_client


def _chat(client, message: str) -> str:
    response = client.post("/api/chat", json={"message": message})
    payload = response.get_json()
    assert payload is not None, "Chat endpoint did not return JSON"
    return payload["response"]


def _assert_in(response: str, expected: str):
    assert expected.lower() in response.lower(), f"{expected} not found in response: {response}"


def test_find_center_by_code(client):
    response = _chat(client, "I need the center id for code ES0263")
    _assert_in(response, "ES0263")
    _assert_in(response, "Pescadores")


def test_find_center_by_address_and_city(client):
    response = _chat(client, "Padilla 239 in Barcelona")
    _assert_in(response, "Padilla 239")
    _assert_in(response, "ES0323")


def test_find_center_by_name_with_typo(client):
    response = _chat(client, "center id for Sardinia 200 Barcelona")
    _assert_in(response, "ES0284")
    _assert_in(response, "Sardenya 200")


def test_find_multiple_centers_in_city(client):
    response = _chat(client, "centers in Sant Andreu de la Barca Barcelona")
    assert any(code in response for code in ("ES0172", "ES0329")), response

