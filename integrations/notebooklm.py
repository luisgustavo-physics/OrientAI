"""Integração com NotebookLM como base de conhecimento ancorada para cada trilha de estudo."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings, get_settings
from core.models import StudyTrack, TopicNode


class NotebookLMClient:
    """Gerencia a ancoragem entre trilhas de estudo e seus respectivos cadernos do NotebookLM."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def provision_notebook_for_track(self, track: StudyTrack) -> str:
        """Garante ou gera um identificador único de caderno para a trilha."""
        if not track.notebook_id:
            track.notebook_id = f"nlm_{track.id}"
        return track.notebook_id

    def add_source(self, track: StudyTrack, source_uri: str) -> None:
        """Associa um documento, livro ou URL ao caderno da trilha."""
        if source_uri not in track.notebook_sources:
            track.notebook_sources.append(source_uri)

    def get_topic_study_brief(self, track: StudyTrack, node: TopicNode) -> Dict[str, Any]:
        """Retorna o briefing de ancoragem no NotebookLM para um nó de estudo."""
        return {
            "notebook_id": track.notebook_id or f"nlm_{track.id}",
            "track_name": track.name,
            "topic_id": node.id,
            "topic_name": node.name,
            "subject": node.subject,
            "notebook_ref": node.notebook_ref or f"Caderno '{track.name}' > Seção '{node.name}'",
            "sources": track.notebook_sources,
            "prompt_for_notebooklm": (
                f"No caderno '{track.name}', sintetize os pontos críticos e pegadinhas conceituais de "
                f"'{node.name}' com base nas fontes carregadas. Gere 3 perguntas de sondagem ativa "
                f"para verificar se o estudante está pronto para o entregável: {node.deliverable_template or 'exercícios práticos'}."
            )
        }
