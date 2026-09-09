"""Knowledge Store Local & Context Injection (Substituto do NotebookLM via Gemini Long Context).

Gerencia a indexação de fontes (.md, .txt, .pdf) por trilha em tracks/sources/<track_id>/
e injeta o contexto ancorado (grounding) nas chamadas do GeminiClient com zero alucinação.
"""

import logging
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}


class KnowledgeStore:
    """Gerenciador local de fontes de conhecimento para ancoragem cognitiva (Grounding)."""

    def __init__(
        self,
        sources_base_dir: Optional[Path] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.sources_base_dir = sources_base_dir or self.settings.resolved_sources_dir
        self.sources_base_dir.mkdir(parents=True, exist_ok=True)

    def _slugify_track(self, track_id: str) -> str:
        text = unicodedata.normalize("NFKD", track_id).encode("ASCII", "ignore").decode("utf-8")
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        return re.sub(r"[\s_-]+", "_", text).strip("_")

    def get_track_sources_dir(self, track_id: str) -> Path:
        """Retorna o diretório de fontes da trilha: tracks/sources/<track_id>/."""
        track_slug = self._slugify_track(track_id)
        path = self.sources_base_dir / track_slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_sources(self, track_id: str) -> List[Dict[str, Any]]:
        """Lista todos os arquivos válidos (.md, .txt, .pdf) na pasta da trilha."""
        track_dir = self.get_track_sources_dir(track_id)
        sources: List[Dict[str, Any]] = []

        if not track_dir.exists():
            return sources

        for item in sorted(track_dir.iterdir()):
            if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
                sources.append({
                    "name": item.name,
                    "path": str(item),
                    "extension": item.suffix.lower(),
                    "size_bytes": item.stat().st_size,
                    "modified_at": item.stat().st_mtime,
                })

        return sources

    def add_source_file(
        self,
        track_id: str,
        file_path: Path,
        destination_name: Optional[str] = None
    ) -> Path:
        """Copia um arquivo externo para o diretório de fontes da trilha."""
        track_dir = self.get_track_sources_dir(track_id)
        dest_filename = destination_name or file_path.name
        dest_path = track_dir / dest_filename
        shutil.copy2(file_path, dest_path)
        return dest_path

    def add_source_text(
        self,
        track_id: str,
        filename: str,
        content: str
    ) -> Path:
        """Escreve diretamente um arquivo de texto/markdown no diretório da trilha."""
        track_dir = self.get_track_sources_dir(track_id)
        if not any(filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
            filename = f"{filename}.md"
        dest_path = track_dir / filename
        dest_path.write_text(content, encoding="utf-8")
        return dest_path

    def extract_file_content(self, file_path: Path) -> str:
        """Extrai texto de arquivos .md, .txt ou .pdf."""
        ext = file_path.suffix.lower()
        if ext in {".md", ".txt"}:
            try:
                return file_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.error(f"Erro ao ler arquivo de texto {file_path}: {e}")
                return ""

        elif ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(file_path))
                pages_text = []
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        pages_text.append(f"[Página {i+1}]\n{text.strip()}")
                return "\n\n".join(pages_text)
            except Exception as e:
                logger.warning(f"Erro ao extrair texto de PDF {file_path}: {e}")
                return f"[Conteúdo do PDF '{file_path.name}' não pôde ser extraído: {e}]"

        return ""

    def load_track_context(
        self,
        track_id: str,
        max_chars: Optional[int] = None
    ) -> str:
        """Carrega e compila todas as fontes indexadas da trilha em um bloco de contexto.

        Emula o comportamento do NotebookLM com ancoragem cognitiva e citação de fontes.
        """
        sources = self.list_sources(track_id)
        if not sources:
            return ""

        blocks: List[str] = [
            f"=== BASE DE CONHECIMENTO ANCORADA DA TRILHA: '{track_id.upper()}' ===",
            "Você possui acesso às fontes autoritativas oficiais abaixo.",
            "Todas as definições, teoremas, algoritmos e exercícios gerados devem ser",
            "estritamente fundamentados (grounded) nestes documentos (NotebookLM Grounding Mode).\n"
        ]

        total_chars = 0
        for src in sources:
            path = Path(src["path"])
            content = self.extract_file_content(path)
            if not content.strip():
                continue

            file_header = f"--- FONTE: {src['name']} ({src['extension'].upper()}) ---"
            file_block = f"{file_header}\n{content}\n"

            if max_chars and (total_chars + len(file_block) > max_chars):
                remaining = max_chars - total_chars
                if remaining > 200:
                    blocks.append(file_block[:remaining] + "\n[... Fonte truncada pelo limite de caracteres ...]\n")
                break

            blocks.append(file_block)
            total_chars += len(file_block)

        blocks.append("=== FIM DAS FONTES ANCORADAS ===")
        return "\n".join(blocks)

    def get_grounded_system_instruction(
        self,
        track_id: str,
        base_instruction: Optional[str] = None
    ) -> str:
        """Gera a instrução de sistema injetando as fontes da trilha para ancoragem estrita."""
        default_base = (
            "Você é um tutor pedagógico e curador de questões de alto rendimento do OrientAI.\n"
            "Atue com rigor técnico, máxima clareza e fidelidade aos livros-texto e bancas de referência."
        )
        instruction = (base_instruction or default_base).strip()
        context = self.load_track_context(track_id)

        if context:
            return f"{instruction}\n\n{context}\n\nDiretriz Anti-Alucinação: Responda fundamentando-se nas fontes acima sempre que aplicável."
        return instruction

    def index_summary(self, track_id: str) -> Dict[str, Any]:
        """Retorna resumo da indexação da base de conhecimento da trilha."""
        sources = self.list_sources(track_id)
        total_chars = 0
        for src in sources:
            content = self.extract_file_content(Path(src["path"]))
            total_chars += len(content)

        return {
            "track_id": track_id,
            "sources_dir": str(self.get_track_sources_dir(track_id)),
            "total_files": len(sources),
            "files": [s["name"] for s in sources],
            "total_characters": total_chars,
        }
