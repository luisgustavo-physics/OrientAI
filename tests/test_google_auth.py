"""Testes unitários para autenticação Google AI Studio (GeminiClient, GoogleAuthManager e CLI auth)."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from config.settings import Settings
from integrations.gemini_client import GeminiClient
from integrations.google_auth import GoogleAuthManager
from cli.interface import (
    build_parser,
    handle_auth_login,
    handle_auth_logout,
    handle_auth_setup_key,
    handle_auth_status,
)


class DummySchema(BaseModel):
    message: str
    count: int


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """Cria settings temporário isolado em tmp_path com .env próprio."""
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        gemini_api_key=None,
    )
    return settings


@pytest.fixture
def auth_manager(mock_settings: Settings) -> GoogleAuthManager:
    return GoogleAuthManager(settings=mock_settings)


# ----------------- Testes do GoogleAuthManager -----------------

def test_auth_manager_no_key_initially(auth_manager: GoogleAuthManager):
    """Quando não há chave configurada, deve retornar None e is_authenticated False."""
    assert auth_manager.get_api_key() is None
    assert auth_manager.is_authenticated() is False


def test_auth_manager_save_and_get_api_key(auth_manager: GoogleAuthManager):
    """Testa salvamento da chave no .env e recuperação correta."""
    test_key = "AIzaSy_FAKE_TEST_KEY_12345"
    saved = auth_manager.save_api_key(test_key)
    assert saved is True
    assert auth_manager.get_api_key() == test_key
    assert auth_manager.is_authenticated() is True

    # Verifica se o arquivo .env contém a chave
    env_content = auth_manager.env_file.read_text(encoding="utf-8")
    assert f"GEMINI_API_KEY={test_key}" in env_content


def test_auth_manager_logout(auth_manager: GoogleAuthManager):
    """Testa remoção da chave do .env e da memória."""
    auth_manager.save_api_key("AIzaSy_KEY_TO_DELETE_999")
    assert auth_manager.is_authenticated() is True

    logged_out = auth_manager.logout()
    assert logged_out is True
    assert auth_manager.get_api_key() is None or auth_manager.get_api_key() == ""
    assert auth_manager.is_authenticated() is False


def test_auth_manager_get_status(auth_manager: GoogleAuthManager):
    """Verifica dicionário de status retornado."""
    auth_manager.save_api_key("AIzaSy_SAMPLE_KEY_ABCDEF1234")
    status = auth_manager.get_status()

    assert status["authenticated"] is True
    assert status["has_key"] is True
    assert "AIzaSy" in status["masked_key"]
    assert "model" in status


# ----------------- Testes do GeminiClient -----------------

def test_gemini_client_unconfigured():
    """Garante que cliente sem chave levanta ValueError explicativo ao tentar operar."""
    client = GeminiClient(api_key="")
    assert client.is_configured() is False

    with pytest.raises(ValueError, match="Chave de API do Google AI Studio não configurada"):
        client.get_client()


def test_gemini_client_test_connection_success():
    """Testa conexão bem-sucedida mockando generate_content."""
    client = GeminiClient(api_key="AIzaSy_VALID_MOCK_KEY", model="gemini-2.5-flash")
    assert client.is_configured() is True

    mock_resp = MagicMock()
    mock_resp.text = "OK"

    with patch.object(client, "get_client") as mock_get_client, \
         patch("time.sleep", return_value=None):
        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_resp
        mock_sdk_client = MagicMock()
        mock_sdk_client.models = mock_models
        mock_get_client.return_value = mock_sdk_client

        success, msg = client.test_connection()
        assert success is True
        assert "SUCESSO (Ativo via gemini-2.5-flash)" in msg


def test_gemini_client_test_connection_fallback_on_503():
    """Testa failover em cascata quando o modelo primário retorna 503 Service Unavailable."""
    client = GeminiClient(api_key="AIzaSy_VALID_MOCK_KEY", model="gemini-3.6-flash")

    mock_resp_fallback = MagicMock()
    mock_resp_fallback.text = "OK"

    def mock_generate(model, contents, config):
        # Verifica se AFC está desativado na config
        assert config.automatic_function_calling.disable is True
        assert config.tools is None
        # O modelo primário 3.6-flash falha com 503
        if model == "gemini-3.6-flash":
            raise Exception("503 Service Unavailable: High demand on gemini-3.6-flash")
        # O modelo seguinte de fallback responde com sucesso
        return mock_resp_fallback

    with patch.object(client, "get_client") as mock_get_client, \
         patch("time.sleep", return_value=None):
        mock_models = MagicMock()
        mock_models.generate_content.side_effect = mock_generate
        mock_sdk_client = MagicMock()
        mock_sdk_client.models = mock_models
        mock_get_client.return_value = mock_sdk_client

        success, msg = client.test_connection()
        assert success is True
        assert "SUCESSO (Ativo via" in msg
        assert "gemini-3.6-flash" not in msg  # Respondeu via fallback


def test_gemini_client_test_connection_all_fail():
    """Quando todos os modelos candidatos falham, deve retornar erro explicativo."""
    client = GeminiClient(api_key="AIzaSy_VALID_MOCK_KEY")

    with patch.object(client, "get_client") as mock_get_client, \
         patch("time.sleep", return_value=None):
        mock_models = MagicMock()
        mock_models.generate_content.side_effect = Exception("503 UNAVAILABLE: All servers busy")
        mock_sdk_client = MagicMock()
        mock_sdk_client.models = mock_models
        mock_get_client.return_value = mock_sdk_client

        success, msg = client.test_connection()
        assert success is False
        assert "Todos os modelos de fallback falharam" in msg


def test_gemini_client_test_connection_failure():
    """Testa conexão com erro fatal de autenticação (não transitório)."""
    client = GeminiClient(api_key="AIzaSy_INVALID_MOCK_KEY")

    with patch.object(client, "get_client") as mock_get_client:
        mock_models = MagicMock()
        mock_models.generate_content.side_effect = Exception("API_KEY_INVALID: Chave rejeitada")
        mock_sdk_client = MagicMock()
        mock_sdk_client.models = mock_models
        mock_get_client.return_value = mock_sdk_client

        success, msg = client.test_connection()
        assert success is False
        assert "API_KEY_INVALID" in msg


def test_gemini_client_generate_text():
    """Testa generate_text com resposta mockada."""
    client = GeminiClient(api_key="AIzaSy_VALID_MOCK_KEY")
    mock_resp = MagicMock()
    mock_resp.text = "Resposta conceitual detalhada sobre Grafos."

    with patch.object(client, "get_client") as mock_get_client:
        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_resp
        mock_sdk_client = MagicMock()
        mock_sdk_client.models = mock_models
        mock_get_client.return_value = mock_sdk_client

        text = client.generate_text("Explique grafos")
        assert "Resposta conceitual" in text


def test_gemini_client_generate_structured_pydantic():
    """Testa generate_structured retornando objeto validado Pydantic."""
    client = GeminiClient(api_key="AIzaSy_VALID_MOCK_KEY")
    mock_resp = MagicMock()
    mock_resp.parsed = DummySchema(message="Sucesso total", count=42)
    mock_resp.text = '{"message": "Sucesso total", "count": 42}'

    with patch.object(client, "get_client") as mock_get_client:
        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_resp
        mock_sdk_client = MagicMock()
        mock_sdk_client.models = mock_models
        mock_get_client.return_value = mock_sdk_client

        result = client.generate_structured(
            prompt="Gere dados",
            response_schema=DummySchema
        )
        assert isinstance(result, DummySchema)
        assert result.message == "Sucesso total"
        assert result.count == 42


# ----------------- Testes dos Comandos CLI -----------------

def test_cli_parser_auth_commands():
    """Verifica se os comandos 'setup-key', 'login', 'status', 'logout' funcionam no parser."""
    parser = build_parser()

    # setup-key com --key
    args_setup = parser.parse_args(["auth", "setup-key", "--key", "AIzaSy_TEST_KEY"])
    assert args_setup.command == "auth"
    assert args_setup.auth_action == "setup-key"
    assert args_setup.key == "AIzaSy_TEST_KEY"

    # login com alias
    args_login = parser.parse_args(["auth", "login", "--key", "AIzaSy_TEST_KEY_2"])
    assert args_login.command == "auth"
    assert args_login.auth_action == "login"
    assert args_login.key == "AIzaSy_TEST_KEY_2"

    # status
    args_status = parser.parse_args(["auth", "status"])
    assert args_status.command == "auth"
    assert args_status.auth_action == "status"

    # logout
    args_logout = parser.parse_args(["auth", "logout"])
    assert args_logout.command == "auth"
    assert args_logout.auth_action == "logout"


def test_cli_auth_handlers_execution(mock_settings: Settings):
    """Testa os handlers da CLI sem requisições reais de rede."""
    with patch("cli.interface.get_settings", return_value=mock_settings), \
         patch("integrations.google_auth.GeminiClient.test_connection", return_value=(True, "Ping OK")):

        # setup-key
        handle_auth_setup_key(argparse.Namespace(key="AIzaSy_CLI_MOCK_KEY_12345"))
        assert mock_settings.gemini_api_key == "AIzaSy_CLI_MOCK_KEY_12345"

        # status
        handle_auth_status(argparse.Namespace())

        # login (alias)
        handle_auth_login(argparse.Namespace(key="AIzaSy_CLI_MOCK_KEY_67890"))
        assert mock_settings.gemini_api_key == "AIzaSy_CLI_MOCK_KEY_67890"

        # logout
        handle_auth_logout(argparse.Namespace())
        assert mock_settings.gemini_api_key is None
