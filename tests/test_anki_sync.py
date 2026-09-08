"""Testes unitários para a integração com o AnkiConnect e fallback offline (integrations/anki_sync.py)."""

import json
from unittest.mock import MagicMock, patch
import pytest

from config.settings import Settings
from integrations.anki_sync import AnkiClient, AnkiConnectError


@pytest.fixture
def anki_env(tmp_path):
    """Ambiente isolado para testes do AnkiClient."""
    settings = Settings(
        data_dir=tmp_path / "data",
        anki_url="http://localhost:8765",
        anki_timeout_seconds=0.1
    )
    client = AnkiClient(settings)
    return settings, client


def test_offline_detection_and_fallback_queue(anki_env):
    """Testa que quando o Anki está offline, os cards são enfileirados em anki_queue.json sem erro."""
    settings, client = anki_env

    # Anki offline simulado (porta sem serviço ouvindo)
    res = client.create_card(
        deck_name="Unicamp::História",
        front="O que foi o Tratado de Madri (1750)?",
        back="Consagrou o princípio do uti possidetis, redefinindo as fronteiras do Brasil colonial."
    )

    assert res["success"] is True
    assert res["offline"] is True
    assert "fila offline" in res["message"] or "enfileirado" in res["message"]

    # Verifica se o arquivo de fila foi gravado
    queue_file = settings.anki_queue_file
    assert queue_file.exists()

    with open(queue_file, "r", encoding="utf-8") as f:
        queued = json.load(f)

    assert len(queued) == 1
    assert queued[0]["deckName"] == "Unicamp::História"
    assert queued[0]["fields"]["Front"] == "O que foi o Tratado de Madri (1750)?"


def test_stats_when_offline(anki_env):
    """Testa que get_today_stats retorna dicionário limpo e seguro mesmo offline."""
    _, client = anki_env
    stats = client.get_today_stats()

    assert stats["online"] is False
    assert stats["reviewed_today"] == 0
    assert stats["total_pending"] == 0
    assert isinstance(stats["decks_pending"], dict)


def test_online_sync_with_mocked_ankiconnect(anki_env):
    """Testa fluxo online simulado com AnkiConnect respondendo com sucesso."""
    settings, client = anki_env

    # Simula respostas do AnkiConnect
    def mock_post(url, json, timeout):
        action = json.get("action")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        if action == "version":
            mock_resp.json.return_value = {"result": 6, "error": None}
        elif action == "createDeck":
            mock_resp.json.return_value = {"result": 12345, "error": None}
        elif action == "addNote":
            mock_resp.json.return_value = {"result": 987654, "error": None}
        elif action == "getNumCardsReviewedToday":
            mock_resp.json.return_value = {"result": 42, "error": None}
        elif action == "deckNames":
            mock_resp.json.return_value = {"result": ["Unicamp::Física"], "error": None}
        elif action == "getDeckStats":
            mock_resp.json.return_value = {
                "result": {
                    "1": {"name": "Unicamp::Física", "new_count": 5, "learn_count": 3, "review_count": 12}
                },
                "error": None
            }
        else:
            mock_resp.json.return_value = {"result": None, "error": None}

        return mock_resp

    with patch("requests.post", side_effect=mock_post):
        assert client.is_online() is True

        stats = client.get_today_stats()
        assert stats["online"] is True
        assert stats["reviewed_today"] == 42
        assert stats["total_pending"] == 20

        # Criação de card online
        res = client.create_card(
            deck_name="Unicamp::Física",
            front="Segunda Lei de Newton",
            back="F = m * a"
        )
        assert res["success"] is True
        assert res["offline"] is False
        assert res["note_id"] == 987654
