"""Gerenciador Centralizado de Autenticação via Google AI Studio API Key.

Substitui completamente o fluxo legado de OAuth 2.0 (client_secret.json / token.json)
por autenticação via GEMINI_API_KEY, com persistência no .env e teste de conectividade.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config.settings import Settings, get_settings
from integrations.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class GoogleAuthManager:
    """Gerencia autenticação centralizada com Google AI Studio via GEMINI_API_KEY."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.env_file = self.settings.base_dir / ".env"

    def get_api_key(self) -> Optional[str]:
        """Recupera a chave do Google AI Studio a partir do settings, ambiente ou .env."""
        key = self.settings.gemini_api_key or os.getenv("GEMINI_API_KEY")
        if key and key.strip():
            return key.strip()

        # Lê diretamente do .env se existir
        if self.env_file.exists():
            try:
                content = self.env_file.read_text(encoding="utf-8")
                match = re.search(r"^[ \t]*GEMINI_API_KEY[ \t]*=[ \t]*(.*?)[ \t]*$", content, re.MULTILINE)
                if match and match.group(1):
                    val = match.group(1).strip().strip('"').strip("'")
                    if val:
                        return val
            except Exception as e:
                logger.debug(f"Erro ao ler .env: {e}")

        return None

    def is_authenticated(self) -> bool:
        """Verifica se há uma chave de API configurada e com tamanho válido."""
        key = self.get_api_key()
        return bool(key and len(key) >= 10)

    def save_api_key(self, api_key: str) -> bool:
        """Salva ou atualiza a chave GEMINI_API_KEY no arquivo .env e na memória."""
        clean_key = api_key.strip().strip('"').strip("'")
        if not clean_key:
            return False

        # Atualiza em memória
        os.environ["GEMINI_API_KEY"] = clean_key
        self.settings.gemini_api_key = clean_key

        # Persiste no .env
        try:
            if not self.env_file.exists():
                self.env_file.write_text(f"GEMINI_API_KEY={clean_key}\n", encoding="utf-8")
                return True

            content = self.env_file.read_text(encoding="utf-8")
            if re.search(r"^[ \t]*GEMINI_API_KEY[ \t]*=.*$", content, re.MULTILINE):
                new_content = re.sub(
                    r"^[ \t]*GEMINI_API_KEY[ \t]*=.*$",
                    f"GEMINI_API_KEY={clean_key}",
                    content,
                    flags=re.MULTILINE
                )
            else:
                new_content = content.rstrip() + f"\nGEMINI_API_KEY={clean_key}\n"

            self.env_file.write_text(new_content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar chave no .env: {e}")
            return False

    def test_key(self, api_key: Optional[str] = None) -> Tuple[bool, str]:
        """Testa uma chave específica ou a chave ativa cadastrada."""
        key_to_test = api_key or self.get_api_key()
        if not key_to_test:
            return False, "Nenhuma chave fornecida ou configurada."

        client = GeminiClient(api_key=key_to_test, settings=self.settings)
        return client.test_connection()

    def logout(self) -> bool:
        """Remove a GEMINI_API_KEY do arquivo .env e da sessão ativa."""
        os.environ.pop("GEMINI_API_KEY", None)
        self.settings.gemini_api_key = None

        if not self.env_file.exists():
            return True

        try:
            content = self.env_file.read_text(encoding="utf-8")
            new_content = re.sub(
                r"^[ \t]*GEMINI_API_KEY[ \t]*=.*$",
                "GEMINI_API_KEY=",
                content,
                flags=re.MULTILINE
            )
            self.env_file.write_text(new_content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Erro ao remover chave do .env: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Retorna estado detalhado da autenticação Google AI Studio."""
        api_key = self.get_api_key()
        is_auth = self.is_authenticated()

        masked = None
        if api_key:
            if len(api_key) > 8:
                masked = f"{api_key[:6]}...{api_key[-4:]}"
            else:
                masked = "***"

        return {
            "authenticated": is_auth,
            "has_key": bool(api_key),
            "masked_key": masked,
            "model": self.settings.gemini_model,
            "env_file": str(self.env_file),
            "env_file_exists": self.env_file.exists(),
        }
