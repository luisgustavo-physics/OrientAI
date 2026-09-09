"""Cliente Centralizado para Google AI Studio (Gemini API) com Resiliência e Fallback.

Fornece interface padronizada para geração de texto e saídas estruturadas
tipadas com Pydantic, com supressão de warnings de AFC, retry exponencial
e failover em cascata contra erros temporários (503 Service Unavailable, 429, etc.).
"""

import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel

from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# Silencia avisos informativos internos do SDK google-genai
logging.getLogger("google.genai.models").setLevel(logging.ERROR)
logging.getLogger("google.genai").setLevel(logging.ERROR)

T = TypeVar("T", bound=BaseModel)

# Lista de modelos padrão para failover em cascata
DEFAULT_FALLBACK_MODELS = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-1.5-flash",
]


class GeminiClient:
    """Cliente oficial para Google AI Studio / Gemini API com fallback e retries."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = (
                self.settings.gemini_api_key
                or os.getenv("GEMINI_API_KEY")
            )
        self.model = model or self.settings.gemini_model or "gemini-2.5-flash"
        self.active_model: str = self.model
        self._client = None

    def is_configured(self) -> bool:
        """Retorna True se a chave de API estiver definida e não vazia."""
        return bool(self.api_key and self.api_key.strip())

    def get_client(self):
        """Retorna instância autenticada do SDK oficial google-genai.

        Levanta ValueError com mensagem clara se a chave não estiver configurada.
        """
        if not self.is_configured():
            raise ValueError(
                "Chave de API do Google AI Studio não configurada.\n"
                "Defina GEMINI_API_KEY no seu arquivo .env ou execute: python main.py auth setup-key"
            )

        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key.strip())

        return self._client

    def get_fallback_candidates(self) -> List[str]:
        """Retorna a lista ordenada e sem duplicatas de modelos candidatos para fallback."""
        candidates = [self.model]
        for m in DEFAULT_FALLBACK_MODELS:
            if m not in candidates:
                candidates.append(m)
        return candidates

    @staticmethod
    def _is_transient_error(e: Exception) -> bool:
        """Verifica se o erro é transitório (503 Service Unavailable, 429 Rate Limit, etc.)."""
        msg = str(e).upper()
        transient_indicators = [
            "503", "UNAVAILABLE", "HIGH DEMAND",
            "429", "RESOURCE_EXHAUSTED", "RATE_LIMIT", "QUOTA",
            "500", "INTERNAL", "TIMEOUT", "DEADLINE_EXCEEDED"
        ]
        return any(ind in msg for ind in transient_indicators)

    def _execute_with_retry_and_fallback(
        self,
        operation_fn: Callable[[str], Any],
        max_retries_per_model: int = 2,
        retry_delays: Tuple[float, ...] = (1.0, 2.0),
    ) -> Tuple[Any, str]:
        """Executa operação com retry exponencial e failover em cascata de modelos.

        Args:
            operation_fn: Função que recebe (model_name: str) e executa a chamada.
            max_retries_per_model: Quantidade de retries antes de passar ao próximo modelo.
            retry_delays: Intervalos de espera exponencial (segundos).

        Retorna:
            (resultado, modelo_que_respondeu)
        """
        candidates = self.get_fallback_candidates()
        last_exception = None

        for idx, candidate_model in enumerate(candidates):
            for attempt in range(max_retries_per_model + 1):
                try:
                    result = operation_fn(candidate_model)
                    self.active_model = candidate_model
                    if idx > 0 or attempt > 0:
                        logger.info(
                            f"Chamada bem-sucedida no modelo '{candidate_model}' "
                            f"(fallback índice {idx}, tentativa {attempt + 1})"
                        )
                    return result, candidate_model
                except Exception as e:
                    last_exception = e
                    if not self._is_transient_error(e):
                        # Erros fatais (ex: chave inválida ou schema incorreto) não se beneficiam de fallback de modelo
                        raise

                    if attempt < max_retries_per_model:
                        delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                        logger.warning(
                            f"Modelo '{candidate_model}' retornou erro transitório ({e}). "
                            f"Tentativa {attempt + 1}/{max_retries_per_model + 1}. Aguardando {delay}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.warning(
                            f"Modelo '{candidate_model}' esgotou {max_retries_per_model + 1} tentativas ({e}). "
                            f"Acionando failover para próximo modelo candidato..."
                        )

        raise last_exception or RuntimeError("Todos os modelos candidatos de fallback falharam.")

    def test_connection(self) -> Tuple[bool, str]:
        """Testa a chave com um ping rápido no Google AI Studio com retry e failover de modelos.

        Retorna:
            (True, mensagem_sucesso) em caso de sucesso
            (False, mensagem_erro) em caso de falha
        """
        if not self.is_configured():
            return False, "Chave GEMINI_API_KEY não configurada no ambiente ou .env."

        try:
            client = self.get_client()
            from google.genai import types

            # Desativa explicitamente AFC para suprimir warning do SDK e não declara tools
            config = types.GenerateContentConfig(
                tools=None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )

            def _ping_call(model_name: str):
                return client.models.generate_content(
                    model=model_name,
                    contents="ping",
                    config=config,
                )

            response, active_model = self._execute_with_retry_and_fallback(
                _ping_call,
                max_retries_per_model=2,
                retry_delays=(1.0, 2.0)
            )

            if response and response.text:
                return True, f"SUCESSO (Ativo via {active_model})"
            return False, "Resposta vazia recebida da API do Google AI Studio."
        except Exception as e:
            err_msg = str(e)
            if "API_KEY_INVALID" in err_msg or "400" in err_msg or "INVALID_ARGUMENT" in err_msg:
                return False, f"Chave de API inválida: {err_msg}"
            return False, f"Todos os modelos de fallback falharam: {err_msg}"

    def generate_text(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Gera texto com Gemini aplicando supressão de AFC e fallback em cascata."""
        client = self.get_client()
        from google.genai import types

        config = types.GenerateContentConfig(
            tools=None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            system_instruction=system_instruction,
        )

        def _text_call(model_name: str):
            return client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )

        try:
            response, _ = self._execute_with_retry_and_fallback(_text_call)
            return response.text or ""
        except Exception as e:
            logger.error(f"Erro ao gerar texto com Gemini após retries e fallbacks: {e}")
            raise

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
    ) -> T:
        """Gera saída estritamente tipada com base em modelo Pydantic com resiliência a 503."""
        client = self.get_client()
        from google.genai import types

        config = types.GenerateContentConfig(
            tools=None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            response_mime_type="application/json",
            response_schema=response_schema,
            system_instruction=system_instruction,
        )

        def _structured_call(model_name: str):
            return client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )

        try:
            response, _ = self._execute_with_retry_and_fallback(_structured_call)

            # 1. Se o SDK já parseou diretamente no schema
            if getattr(response, "parsed", None) is not None:
                if isinstance(response.parsed, response_schema):
                    return response.parsed
                if isinstance(response.parsed, dict):
                    return response_schema.model_validate(response.parsed)

            # 2. Fallback: parse manual do JSON retornado em text
            raw_text = response.text or "{}"
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()

            data = json.loads(raw_text)
            return response_schema.model_validate(data)
        except Exception as e:
            logger.error(f"Erro ao gerar conteúdo estruturado com Gemini após retries e fallbacks: {e}")
            raise


_gemini_client_instance: Optional[GeminiClient] = None


def get_gemini_client(settings: Optional[Settings] = None) -> GeminiClient:
    """Retorna instância singleton do GeminiClient."""
    global _gemini_client_instance
    if _gemini_client_instance is None:
        _gemini_client_instance = GeminiClient(settings=settings)
    return _gemini_client_instance
