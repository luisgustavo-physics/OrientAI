"""Integração com NotebookLM / Knowledge Store ancorado para cada trilha de estudo."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings, get_settings
from core.models import StudyTrack, TopicNode
from core.knowledge_store import KnowledgeStore


class NotebookLMClient:
    """Gerencia a ancoragem entre trilhas de estudo e a base de conhecimento (NotebookLM / KnowledgeStore)."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        knowledge_store: Optional[KnowledgeStore] = None
    ):
        self.settings = settings or get_settings()
        self.knowledge_store = knowledge_store or KnowledgeStore(settings=self.settings)

    def provision_notebook_for_track(self, track: StudyTrack) -> str:
        """Garante ou gera um identificador único de caderno para a trilha e prepara a pasta de fontes."""
        if not track.notebook_id:
            track.notebook_id = f"nlm_{track.id}"
        # Garante diretório de fontes da trilha
        self.knowledge_store.get_track_sources_dir(track.id)
        return track.notebook_id

    def add_source(self, track: StudyTrack, source_uri: str) -> None:
        """Associa um documento, livro ou URL ao caderno da trilha e à base local."""
        if source_uri not in track.notebook_sources:
            track.notebook_sources.append(source_uri)

        # Se for um arquivo local existente, copia para tracks/sources/<track_id>/
        path = Path(source_uri)
        if path.exists() and path.is_file():
            self.knowledge_store.add_source_file(track.id, path)

    def get_topic_study_brief(self, track: StudyTrack, node: TopicNode) -> Dict[str, Any]:
        """Retorna o briefing de ancoragem no NotebookLM / Knowledge Store para um nó de estudo."""
        local_sources = self.knowledge_store.list_sources(track.id)
        all_sources = list(track.notebook_sources)
        for s in local_sources:
            if s["name"] not in all_sources:
                all_sources.append(s["name"])

        return {
            "notebook_id": track.notebook_id or f"nlm_{track.id}",
            "track_name": track.name,
            "topic_id": node.id,
            "topic_name": node.name,
            "subject": node.subject,
            "notebook_ref": node.notebook_ref or f"Caderno '{track.name}' > Seção '{node.name}'",
            "sources": all_sources,
            "local_sources_count": len(local_sources),
            "prompt_for_notebooklm": (
                f"No caderno '{track.name}', sintetize os pontos críticos e pegadinhas conceituais de "
                f"'{node.name}' com base nas fontes carregadas. Gere 3 perguntas de sondagem ativa "
                f"para verificar se o estudante está pronto para o entregável: {node.deliverable_template or 'exercícios práticos'}."
            )
        }
