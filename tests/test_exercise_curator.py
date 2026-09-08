"""Testes unitários para o ExerciseCurator e integração com GoogleDocsClient."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.exercise_curator import ExerciseCurator
from core.models import ExerciseItem, ExerciseList
from integrations.gdocs_client import GoogleDocsClient


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

    # Verifica se os IDs e gabaritos estão preenchidos
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


def test_gdocs_client_graceful_fallback_to_markdown(tmp_path):
    """Testa o fallback para Markdown local quando credentials.json não existe."""
    curator = ExerciseCurator()
    exercise_list = curator.curate_exercise_list(
        topic_name="Cálculo I: Integrais Definidas",
        track_id="faculdade_computacao"
    )

    worksheets_test_dir = tmp_path / "worksheets"
    client = GoogleDocsClient(
        credentials_path=str(tmp_path / "non_existent_credentials.json"),
        token_path=str(tmp_path / "non_existent_token.json"),
        worksheets_dir=str(worksheets_test_dir)
    )

    result_path = client.create_exercise_doc(
        title="OrientAI — Lista de Exercícios: Integrais Definidas",
        exercise_list=exercise_list
    )

    assert not result_path.startswith("http")
    assert os.path.exists(result_path)
    assert result_path.endswith(".md")

    content = Path(result_path).read_text(encoding="utf-8")
    assert "OrientAI — Lista de Exercícios Tangíveis" in content
    assert "Integrais Definidas" in content
    assert "Nível 1" in content
    assert "Nível 2" in content
    assert "Nível 3" in content
    assert "Gabarito Oficial e Critérios de Correção" in content
    assert "RASCUNHO / DEMONSTRAÇÃO DISCURSIVA" in content


def test_gdocs_client_mock_remote_creation():
    """Testa a criação no Google Docs quando os serviços estão autenticados (mockados)."""
    curator = ExerciseCurator()
    exercise_list = curator.curate_exercise_list("Álgebra Linear", "faculdade_computacao")

    client = GoogleDocsClient()

    mock_docs = MagicMock()
    mock_drive = MagicMock()

    mock_docs.documents().create().execute.return_value = {"documentId": "mock_doc_id_12345"}
    mock_docs.documents().batchUpdate().execute.return_value = {}

    with patch.object(client, "_get_services", return_value=(mock_docs, mock_drive)):
        url = client.create_exercise_doc("Lista Álgebra", exercise_list)

        assert url == "https://docs.google.com/document/d/mock_doc_id_12345/edit"
        mock_docs.documents().create.assert_called()
        mock_docs.documents().batchUpdate.assert_called()
