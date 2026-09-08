"""Integração com o AnkiConnect com fallback resiliente para offline."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from config.settings import Settings, get_settings


class AnkiConnectError(Exception):
    """Exceção levantada para erros retornados pelo AnkiConnect."""
    pass


class AnkiClient:
    """Cliente HTTP para comunicação com a API local do AnkiConnect."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.url = self.settings.anki_url
        self.timeout = self.settings.anki_timeout_seconds
        self.queue_file = self.settings.anki_queue_file

    def _invoke(self, action: str, **params: Any) -> Any:
        """Executa uma chamada RPC para o AnkiConnect."""
        payload = {
            "action": action,
            "version": 6,
            "params": params
        }
        try:
            response = requests.post(self.url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if len(data) != 2:
                raise AnkiConnectError("Resposta do AnkiConnect possui formato inválido.")
            if "error" not in data or "result" not in data:
                raise AnkiConnectError("Resposta não contém chaves esperadas 'error' ou 'result'.")
            if data["error"]:
                raise AnkiConnectError(str(data["error"]))
            return data["result"]
        except (requests.RequestException, ValueError) as err:
            raise ConnectionError(f"Falha ao conectar com AnkiConnect ({self.url}): {err}")

    def is_online(self) -> bool:
        """Verifica se o AnkiConnect está em execução e respondendo."""
        try:
            version = self._invoke("version")
            return version is not None
        except Exception:
            return False

    def get_pending_reviews(self) -> Dict[str, int]:
        """Obtém o número de cards pendentes (review + learn + new) por deck."""
        if not self.is_online():
            return {}

        try:
            deck_names = self._invoke("deckNames")
            if not deck_names:
                return {}
            
            stats_raw = self._invoke("getDeckStats", decks=deck_names)
            pending_by_deck: Dict[str, int] = {}
            
            for deck_id_str, stat in stats_raw.items():
                name = stat.get("name", "Unknown")
                new_count = stat.get("new_count", 0)
                learn_count = stat.get("learn_count", 0)
                review_count = stat.get("review_count", 0)
                total = new_count + learn_count + review_count
                if total > 0:
                    pending_by_deck[name] = total

            return pending_by_deck
        except Exception:
            return {}

    def get_today_stats(self) -> Dict[str, Any]:
        """Extrai métricas consolidadas de revisão do dia no Anki."""
        online = self.is_online()
        if not online:
            return {
                "online": False,
                "reviewed_today": 0,
                "total_pending": 0,
                "decks_pending": {},
                "queued_offline_cards": len(self._load_queue())
            }

        try:
            reviewed_today = self._invoke("getNumCardsReviewedToday")
            pending_decks = self.get_pending_reviews()
            total_pending = sum(pending_decks.values())

            return {
                "online": True,
                "reviewed_today": int(reviewed_today) if reviewed_today else 0,
                "total_pending": total_pending,
                "decks_pending": pending_decks,
                "queued_offline_cards": len(self._load_queue())
            }
        except Exception:
            return {
                "online": False,
                "reviewed_today": 0,
                "total_pending": 0,
                "decks_pending": {},
                "queued_offline_cards": len(self._load_queue())
            }

    def create_card(
        self,
        deck_name: str,
        front: str,
        back: str,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Cria um flashcard pergunta/resposta no Anki ou salva na fila offline."""
        tags = tags or ["orientai", "unicamp"]
        card_data = {
            "deckName": deck_name,
            "modelName": "Basic",
            "fields": {
                "Front": front,
                "Back": back
            },
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck"
            },
            "tags": tags
        }

        if self.is_online():
            try:
                # Assegura que o deck existe
                self._invoke("createDeck", deck=deck_name)
                note_id = self._invoke("addNote", note=card_data)
                return {
                    "success": True,
                    "offline": False,
                    "note_id": note_id,
                    "message": f"Card criado com sucesso no deck '{deck_name}' (ID: {note_id})."
                }
            except Exception as err:
                # Se falhou mesmo online, envia para fila de fallback
                self._enqueue_offline_card(card_data)
                return {
                    "success": True,
                    "offline": True,
                    "message": f"Erro na criação ({err}). Card salvo na fila offline."
                }
        else:
            self._enqueue_offline_card(card_data)
            return {
                "success": True,
                "offline": True,
                "message": f"Anki offline. Card enfileirado para sincronização em '{self.queue_file.name}'."
            }

    def _load_queue(self) -> List[Dict[str, Any]]:
        """Carrega a fila de cards pendentes offline."""
        if not self.queue_file.exists():
            return []
        try:
            with open(self.queue_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _enqueue_offline_card(self, card_data: Dict[str, Any]) -> None:
        """Adiciona um card à fila local para sincronização futura."""
        queue = self._load_queue()
        queue.append(card_data)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.queue_file, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2, ensure_ascii=False)

    def flush_queue(self) -> int:
        """Tenta sincronizar os cards enfileirados offline para o AnkiConnect."""
        if not self.is_online():
            return 0

        queue = self._load_queue()
        if not queue:
            return 0

        synced_count = 0
        remaining_queue: List[Dict[str, Any]] = []

        for card in queue:
            try:
                self._invoke("createDeck", deck=card["deckName"])
                self._invoke("addNote", note=card)
                synced_count += 1
            except Exception:
                remaining_queue.append(card)

        with open(self.queue_file, "w", encoding="utf-8") as f:
            json.dump(remaining_queue, f, indent=2, ensure_ascii=False)

        return synced_count
