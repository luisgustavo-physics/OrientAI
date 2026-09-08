"""Testes unitários para o gerenciador de trilhas de estudo (core/tracks.py)."""

import json
from pathlib import Path
import pytest

from config.settings import Settings
from core.models import StudyTrack, SubjectConfig
from core.tracks import TrackManager


@pytest.fixture
def tracks_env(tmp_path):
    """Cria ambiente isolado com diretório temporário para trilhas."""
    settings = Settings(data_dir=tmp_path / "data")
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir(parents=True, exist_ok=True)
    manager = TrackManager(settings=settings, tracks_dir=tracks_dir)
    return settings, tracks_dir, manager


def test_load_and_create_track(tracks_env):
    """Testa criação e recuperação de uma nova trilha."""
    settings, tracks_dir, manager = tracks_env

    track = StudyTrack(
        id="concurso_bacen",
        name="Concurso BACEN — TI e Ciência de Dados",
        description="Preparação para área de tecnologia do Banco Central",
        target_date="2026-11-15",
        is_active=True,
        subjects={
            "banco_dados": SubjectConfig(
                id="banco_dados",
                name="Banco de Dados & SQL",
                subject_type="computacao",
                weight=3.0,
                weekly_questions_goal=25,
                requires_tangible_deliverable=True,
                deliverable_templates=["Resolver 10 queries complexas com Window Functions e CTEs"]
            )
        }
    )

    created_path = manager.create_track(track)
    assert created_path.exists()

    loaded = manager.get_track("concurso_bacen")
    assert loaded is not None
    assert loaded.id == "concurso_bacen"
    assert loaded.name == "Concurso BACEN — TI e Ciência de Dados"
    assert "banco_dados" in loaded.subjects
    assert loaded.subjects["banco_dados"].weight == 3.0


def test_toggle_track_active_status(tracks_env):
    """Testa ativação e desativação de uma trilha."""
    _, _, manager = tracks_env

    track = StudyTrack(
        id="trilha_teste",
        name="Trilha Teste",
        description="Teste de alternância",
        is_active=True
    )
    manager.create_track(track)

    assert manager.get_track("trilha_teste").is_active is True

    # Desativa
    manager.toggle_track("trilha_teste")
    assert manager.get_track("trilha_teste").is_active is False

    # Ativa novamente
    manager.toggle_track("trilha_teste", is_active=True)
    assert manager.get_track("trilha_teste").is_active is True


def test_find_subject_track(tracks_env):
    """Testa localização automática de matéria por ID ou nome."""
    _, _, manager = tracks_env

    track = StudyTrack(
        id="ia_track",
        name="Trilha IA",
        description="IA e Redes",
        is_active=True,
        subjects={
            "deep_learning": SubjectConfig(
                id="deep_learning",
                name="Deep Learning",
                subject_type="computacao",
                weight=2.5
            )
        }
    )
    manager.create_track(track)

    # Busca por ID
    found_id = manager.find_subject_track("deep_learning")
    assert found_id is not None
    assert found_id[0].id == "ia_track"
    assert found_id[1].name == "Deep Learning"

    # Busca por nome
    found_name = manager.find_subject_track("Deep Learning")
    assert found_name is not None
    assert found_name[0].id == "ia_track"

    # Busca inexistente
    assert manager.find_subject_track("disciplina_fantasma") is None
