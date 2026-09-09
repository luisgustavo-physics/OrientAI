"""Testes unitários para o ExerciseCurator e geração de entregáveis em Markdown e HTML."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.exercise_curator import ExerciseCurator
from core.knowledge_store import KnowledgeStore
from core.models import ExerciseItem, ExerciseList
from integrations.gdocs_client import GoogleDocsClient
from integrations.gemini_client import GeminiClient


def test_exercise_curator_levels_distribution():
    """Garante que a lista gerada possui estritamente 3 N1, 4 N2 e 3 N3."""
    curator = ExerciseCurator()
    exercise_list = curator.curate_exercise_list(
        topic_name="Geometria Analítica: Cônicas",
        track_id="comvest"
    )

    assert isinstance(exercise_list, ExerciseList)
    assert len(exercise_list.exercises) == 10

    lvl1 = [e for e in exercise_list.exercises if e.level == 1]
    lvl2 = [e for e in exercise_list.exercises if e.level == 2]
    lvl3 = [e for e in exercise_list.exercises if e.level == 3]

    assert len(lvl1) == 3
    assert len(lvl2) == 4
    assert len(lvl3) == 3

    for ex in exercise_list.exercises:
        assert ex.id
        assert ex.statement
        assert ex.answer_key
        assert ex.level in [1, 2, 3]


def test_exercise_curator_source_scope_resolution():
    """Valida a resolução automática do escopo de fontes conforme a trilha."""
    curator = ExerciseCurator()

    # Comvest / Unicamp
    list_comvest = curator.curate_exercise_list("Trigonometria", "comvest")
    assert "Comvest" in list_comvest.source_scope or "Unicamp" in list_comvest.source_scope

    # Faculdade / Cálculo
    list_faculdade = curator.curate_exercise_list("Cálculo: Derivadas", "faculdade_computacao")
    assert "Guidorizzi" in list_faculdade.source_scope or "Stewart" in list_faculdade.source_scope

    # Escopo customizado explícito
    custom_scope = "Provas Oficiais MIT OCW 18.01"
    list_custom = curator.curate_exercise_list("Limites", "faculdade_computacao", source_scope=custom_scope)
    assert list_custom.source_scope == custom_scope


def test_exercise_curator_with_mocked_gemini_client(tmp_path: Path):
    """Garante que o curator invoca o GeminiClient quando configurado."""
    mock_gemini = MagicMock(spec=GeminiClient)
    mock_gemini.is_configured.return_value = True

    # Cria uma lista válida de resposta mockada
    mock_list = ExerciseCurator()._generate_fallback_list(
        topic_name="Álgebra Linear: Autovalores",
        track_id="faculdade_computacao",
        scope="Steinbruch",
        target_accuracy=0.85
    )
    mock_gemini.generate_structured.return_value = mock_list

    ks = KnowledgeStore(sources_base_dir=tmp_path / "sources")
    ks.add_source_text("faculdade_computacao", "autovalores.md", "Teorema Espectral e Matrizes Simétricas")

    curator = ExerciseCurator(gemini_client=mock_gemini, knowledge_store=ks)
    result = curator.curate_exercise_list(
        topic_name="Álgebra Linear: Autovalores",
        track_id="faculdade_computacao"
    )

    assert result == mock_list
    mock_gemini.generate_structured.assert_called_once()
    # Verifica se a chamada continha instrução com grounding
    call_kwargs = mock_gemini.generate_structured.call_args.kwargs
    assert "system_instruction" in call_kwargs
    assert "BASE DE CONHECIMENTO ANCORADA" in call_kwargs["system_instruction"]


def test_exercise_curator_save_worksheet_md_and_html(tmp_path: Path):
    """Testa a geração e escrita dos arquivos .md e .html em diretório especificado."""
    curator = ExerciseCurator()
    exercise_list = curator.curate_exercise_list(
        topic_name="Cálculo I: Integrais Definidas",
        track_id="faculdade_computacao"
    )

    out_dir = tmp_path / "worksheets"
    md_path, html_path = curator.save_worksheet(
        exercise_list=exercise_list,
        output_dir=out_dir,
        generate_html=True
    )

    assert md_path.exists()
    assert md_path.name == "faculdade_computacao_calculo_i_integrais_definidas.md"
    md_content = md_path.read_text(encoding="utf-8")
    assert "OrientAI — Lista de Exercícios" in md_content
    assert "Integrais Definidas" in md_content
    assert "Gabarito Oficial e Critérios de Correção" in md_content

    assert html_path is not None
    assert html_path.exists()
    assert html_path.name == "faculdade_computacao_calculo_i_integrais_definidas.html"
    html_content = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_content
    assert "Integrais Definidas" in html_content
    assert "Gabarito Oficial & Critérios de Correção" in html_content
    assert "@media print" in html_content


def test_exercise_list_pydantic_validation_fails_on_imbalance():
    """Garante que o validador do Pydantic rejeita listas com distribuição incorreta de níveis."""
    items = [
        ExerciseItem(id="1", level=1, level_name="N1", statement="Q1", answer_key="A1"),
        ExerciseItem(id="2", level=1, level_name="N1", statement="Q2", answer_key="A2"),
        ExerciseItem(id="3", level=2, level_name="N2", statement="Q3", answer_key="A3"),
    ]

    with pytest.raises(ValueError, match="ExerciseList deve conter exatamente 3 questões de Nível 1"):
        ExerciseList(
            track_id="test",
            topic_name="Test Topic",
            source_scope="Test Scope",
            exercises=items
        )


def test_gdocs_client_local_export(tmp_path: Path):
    """Garante que GoogleDocsClient exporta via geração local sem necessidade de OAuth."""
    curator = ExerciseCurator()
    exercise_list = curator.curate_exercise_list("Álgebra", "faculdade_computacao")

    client = GoogleDocsClient(worksheets_dir=str(tmp_path / "worksheets"))
    result_path = client.create_exercise_doc("Lista Álgebra", exercise_list)

    assert Path(result_path).exists()
    assert result_path.endswith(".md")
