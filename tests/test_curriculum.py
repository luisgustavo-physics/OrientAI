"""Testes unitários para o CurriculumAgent e integração com NotebookLM (core/curriculum.py)."""

# pyrefly: ignore [missing-import]
import pytest

from core.curriculum import CurriculumAgent
from core.graph_engine import GraphEngine
from core.models import TopicStatus
from integrations.notebooklm import NotebookLMClient


def test_generate_guided_curriculum_origin_to_destination():
    """Testa geração de cadeia de nós conectando Teoria da Computação até Criptografia."""
    agent = CurriculumAgent()
    track = agent.generate_guided_curriculum(
        track_id="comp_to_crypto",
        name="Teoria da Computação até Criptografia",
        origin="Teoria da Computação",
        destination="Criptografia Moderna",
        prompt="Modelos formais, aritmética modular, RSA e zero knowledge"
    )

    assert track.id == "comp_to_crypto"
    assert len(track.nodes) >= 4
    assert track.validate_dag() is True

    # Verifica nó de origem e nó terminal
    assert track.origin_node is not None
    assert track.target_node is not None
    assert track.nodes[track.origin_node].status == TopicStatus.UNLOCKED

    # Todos os nós posteriores devem começar bloqueados
    for n_id, node in track.nodes.items():
        if n_id != track.origin_node:
            assert node.status == TopicStatus.LOCKED


def test_notebooklm_ancestry_and_briefing():
    """Testa ancoragem no NotebookLM e briefing de estudo para nós."""
    nlm_client = NotebookLMClient()
    agent = CurriculumAgent(notebook_client=nlm_client)

    track = agent.generate_guided_curriculum(
        track_id="deep_learning_chain",
        name="Deep Learning & LLMs",
        origin="Redes Neurais",
        destination="LLMs e RAG",
        notebook_id="nlm_dl_track"
    )

    assert track.notebook_id == "nlm_dl_track"
    # pyrefly: ignore [bad-index]
    node = track.nodes[track.origin_node]

    brief = nlm_client.get_topic_study_brief(track, node)
    assert brief["notebook_id"] == "nlm_dl_track"
    assert "Redes Neurais" in brief["topic_name"]
    assert "prompt_for_notebooklm" in brief


def test_curriculum_expansion_feedback_loop():
    """Testa retroalimentação curricular quando estudante domina os nós intermediários."""
    agent = CurriculumAgent()
    track = agent.generate_guided_curriculum(
        track_id="ml_track",
        name="ML Foundation",
        origin="Álgebra Linear",
        destination="Modelos Generativos"
    )

    # Simula maestria em todos os nós anteriores ao target
    target_id = track.target_node
    for n_id, node in track.nodes.items():
        if n_id != target_id:
            node.status = TopicStatus.MASTERED

    # Aciona a retroalimentação
    new_node = agent.check_and_expand_curriculum(track)
    assert new_node is not None
    assert "Laboratório de Consolidação" in new_node.name
    assert new_node.id in track.nodes
    assert track.validate_dag() is True
