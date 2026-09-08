"""Testes unitários para o motor de topologia em grafo (DAG) e progressão (core/graph_engine.py)."""

import pytest

from core.graph_engine import GraphEngine
from core.models import ActivityType, StudyBlock, StudyLog, StudyTrack, SubjectConfig, TopicNode, TopicStatus


@pytest.fixture
def sample_dag_track():
    """Cria uma trilha em grafo com 4 nós conectados linearmente e em diamante."""
    # Nó A -> Nó B -> Nó D
    # Nó A -> Nó C -> Nó D
    t = StudyTrack(
        id="dag_test",
        name="Trilha Teste DAG",
        description="Teste de topologia",
        nodes={
            "no_a": TopicNode(
                id="no_a",
                name="Fundamentos A",
                subject="Computação",
                prerequisites=[],
                mastery_threshold=0.80,
                status=TopicStatus.LOCKED
            ),
            "no_b": TopicNode(
                id="no_b",
                name="Tópico B",
                subject="Computação",
                prerequisites=["no_a"],
                mastery_threshold=0.80,
                status=TopicStatus.LOCKED
            ),
            "no_c": TopicNode(
                id="no_c",
                name="Tópico C",
                subject="Computação",
                prerequisites=["no_a"],
                mastery_threshold=0.80,
                status=TopicStatus.LOCKED
            ),
            "no_d": TopicNode(
                id="no_d",
                name="Avançado D",
                subject="Computação",
                prerequisites=["no_b", "no_c"],
                mastery_threshold=0.80,
                status=TopicStatus.LOCKED
            ),
        }
    )
    return t


def test_dag_validation_valid(sample_dag_track):
    """Testa que um grafo acíclico válido é aprovado."""
    assert sample_dag_track.validate_dag() is True


def test_dag_validation_detects_cycle():
    """Testa que um grafo com ciclo é rejeitado com ValueError."""
    cyclic_track = StudyTrack(
        id="cycle_test",
        name="Trilha com Ciclo",
        description="Ciclo",
        nodes={
            "n1": TopicNode(id="n1", name="N1", subject="S", prerequisites=["n3"]),
            "n2": TopicNode(id="n2", name="N2", subject="S", prerequisites=["n1"]),
            "n3": TopicNode(id="n3", name="N3", subject="S", prerequisites=["n2"]),
        }
    )

    with pytest.raises(ValueError, match="Ciclo de dependência detectado"):
        cyclic_track.validate_dag()


def test_dag_validation_detects_nonexistent_prerequisite():
    """Testa erro quando um nó aponta para um pré-requisito que não existe."""
    broken_track = StudyTrack(
        id="broken_test",
        name="Broken",
        description="Broken",
        nodes={
            "n1": TopicNode(id="n1", name="N1", subject="S", prerequisites=["fantasma"]),
        }
    )

    with pytest.raises(ValueError, match="pré-requisito inexistente"):
        broken_track.validate_dag()


def test_initial_unlock_state(sample_dag_track):
    """Testa que initialize_track_graph desbloqueia nós raiz e mantém outros bloqueados."""
    GraphEngine.initialize_track_graph(sample_dag_track)

    assert sample_dag_track.nodes["no_a"].status == TopicStatus.UNLOCKED
    assert sample_dag_track.nodes["no_b"].status == TopicStatus.LOCKED
    assert sample_dag_track.nodes["no_c"].status == TopicStatus.LOCKED
    assert sample_dag_track.nodes["no_d"].status == TopicStatus.LOCKED


def test_unlock_progression_on_mastery(sample_dag_track):
    """Testa que dominar um nó raiz desbloqueia os filhos cujos pré-requisitos foram satisfeitos."""
    GraphEngine.initialize_track_graph(sample_dag_track)

    # 1. Registra estudo no nó A com 70% (abaixo do limiar de 80%)
    mastered, unlocked = GraphEngine.update_topic_progress(
        sample_dag_track,
        topic_id="no_a",
        correct=7,
        total=10,
        deliverable_done=True
    )
    assert mastered is False
    assert unlocked == []
    assert sample_dag_track.nodes["no_a"].status == TopicStatus.IN_PROGRESS
    assert sample_dag_track.nodes["no_b"].status == TopicStatus.LOCKED

    # 2. Registra novo estudo elevando a acurácia para 85%
    mastered, unlocked = GraphEngine.update_topic_progress(
        sample_dag_track,
        topic_id="no_a",
        correct=10,
        total=10,
        deliverable_done=True
    )
    assert mastered is True
    assert "no_b" in unlocked
    assert "no_c" in unlocked
    assert sample_dag_track.nodes["no_a"].status == TopicStatus.MASTERED
    assert sample_dag_track.nodes["no_b"].status == TopicStatus.UNLOCKED
    assert sample_dag_track.nodes["no_c"].status == TopicStatus.UNLOCKED
    # Nó D ainda deve estar LOCKED porque precisa tanto de B quanto de C
    assert sample_dag_track.nodes["no_d"].status == TopicStatus.LOCKED

    # 3. Domina apenas o nó B
    mastered_b, unlocked_b = GraphEngine.update_topic_progress(
        sample_dag_track,
        topic_id="no_b",
        correct=10,
        total=10,
        deliverable_done=True
    )
    assert mastered_b is True
    assert "no_d" not in unlocked_b  # Nó D ainda não pode desbloquear porque falta C
    assert sample_dag_track.nodes["no_d"].status == TopicStatus.LOCKED

    # 4. Domina o nó C -> Agora D deve desbloquear!
    mastered_c, unlocked_c = GraphEngine.update_topic_progress(
        sample_dag_track,
        topic_id="no_c",
        correct=9,
        total=10,
        deliverable_done=True
    )
    assert mastered_c is True
    assert "no_d" in unlocked_c
    assert sample_dag_track.nodes["no_d"].status == TopicStatus.UNLOCKED


def test_get_available_topics(sample_dag_track):
    """Testa que get_available_topics só retorna nós UNLOCKED ou IN_PROGRESS."""
    GraphEngine.initialize_track_graph(sample_dag_track)

    avail = GraphEngine.get_available_topics(sample_dag_track)
    assert len(avail) == 1
    assert avail[0].id == "no_a"
