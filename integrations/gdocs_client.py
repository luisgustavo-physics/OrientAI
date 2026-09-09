"""Exportador de Listas de Exercícios para Markdown e HTML compatível com Google Docs / Obsidian.

Substitui a dependência de autenticação OAuth 2.0 e Google Docs REST API por
geração direta e limpa de arquivos locais prontos para importação ou impressão.
"""

from pathlib import Path
from typing import Any, Optional

from config.settings import Settings, get_settings
from core.models import ExerciseList


class GoogleDocsClient:
    """Cliente exportador de listas de exercícios para Markdown e HTML formatado."""

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        token_path: Optional[str] = None,
        worksheets_dir: Optional[str] = None,
        auth_manager: Optional[Any] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.worksheets_dir = Path(worksheets_dir) if worksheets_dir else self.settings.resolved_worksheets_dir
        self.worksheets_dir.mkdir(parents=True, exist_ok=True)
        self.auth_manager = auth_manager

    def create_exercise_doc(self, title: str, exercise_list: ExerciseList) -> str:
        """Gera arquivo Markdown e HTML local e retorna o caminho do arquivo Markdown gerado."""
        from core.exercise_curator import ExerciseCurator
        curator = ExerciseCurator(settings=self.settings)
        md_path, _ = curator.save_worksheet(
            exercise_list=exercise_list,
            output_dir=self.worksheets_dir,
            generate_html=True
        )
        return str(md_path)
