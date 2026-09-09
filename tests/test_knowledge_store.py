"""Testes unitários para o KnowledgeStore (Grounding Local estilo NotebookLM)."""

from pathlib import Path
import pytest

from core.knowledge_store import KnowledgeStore


@pytest.fixture
def knowledge_store(tmp_path: Path) -> KnowledgeStore:
    sources_dir = tmp_path / "tracks_sources"
    return KnowledgeStore(sources_base_dir=sources_dir)


def test_knowledge_store_track_sources_dir(knowledge_store: KnowledgeStore):
    """Garante a criação do diretório estruturado por trilha."""
    track_dir = knowledge_store.get_track_sources_dir("comvest")
    assert track_dir.exists()
    assert track_dir.is_dir()
    assert track_dir.name == "comvest"


def test_knowledge_store_add_and_list_sources(knowledge_store: KnowledgeStore, tmp_path: Path):
    """Testa adição e listagem de arquivos de fontes (.md, .txt)."""
    # Cria arquivo externo
    ext_file = tmp_path / "apostila_geometria.md"
    ext_file.write_text("# Cônicas e Elipse\nDefinição formal de foco e diretriz.", encoding="utf-8")

    # Adiciona à trilha
    copied_path = knowledge_store.add_source_file("comvest", ext_file)
    assert copied_path.exists()
    assert copied_path.name == "apostila_geometria.md"

    # Adiciona texto direto
    text_path = knowledge_store.add_source_text("comvest", "notas_cinematica", "v = v0 + at")
    assert text_path.exists()
    assert text_path.name == "notas_cinematica.md"

    sources = knowledge_store.list_sources("comvest")
    assert len(sources) == 2
    names = [s["name"] for s in sources]
    assert "apostila_geometria.md" in names
    assert "notas_cinematica.md" in names


def test_knowledge_store_load_track_context(knowledge_store: KnowledgeStore):
    """Verifica compilação de contexto ancorado (Long Context Grounding)."""
    knowledge_store.add_source_text(
        "faculdade",
        "calculo_limites.md",
        "Teorema do Confronto: se g(x) <= f(x) <= h(x)..."
    )

    context = knowledge_store.load_track_context("faculdade")
    assert "BASE DE CONHECIMENTO ANCORADA DA TRILHA: 'FACULDADE'" in context
    assert "calculo_limites.md" in context
    assert "Teorema do Confronto" in context
    assert "FIM DAS FONTES ANCORADAS" in context


def test_knowledge_store_grounded_system_instruction(knowledge_store: KnowledgeStore):
    """Verifica injeção do contexto ancorado na instrução de sistema."""
    # Trilha sem fontes
    inst_empty = knowledge_store.get_grounded_system_instruction("vazia")
    assert "Você é um tutor" in inst_empty
    assert "BASE DE CONHECIMENTO ANCORADA" not in inst_empty

    # Trilha com fontes
    knowledge_store.add_source_text("ia_track", "deep_learning.txt", "Gradiente descendente e backprop")
    inst_grounded = knowledge_store.get_grounded_system_instruction("ia_track")
    assert "BASE DE CONHECIMENTO ANCORADA DA TRILHA: 'IA_TRACK'" in inst_grounded
    assert "Diretriz Anti-Alucinação" in inst_grounded
