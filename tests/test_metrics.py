"""Testes unitários para o módulo de métricas e relatórios multi-trilhas (core/metrics.py)."""

from datetime import date
import json
import pytest

from config.settings import Settings
from config.subjects import DEFAULT_SUBJECTS
from core.metrics import MetricsEngine
from core.models import StudyLog, StudyTrack
from core.state import StateManager
from core.tracks import TrackManager


@pytest.fixture
def test_environment(tmp_path):
    """Cria ambiente isolado com settings, state_manager, tracks e metrics_engine."""
    settings = Settings(
        data_dir=tmp_path / "data",
        daily_study_hours=3.0,
        unicamp_stage_1_date=date(2026, 10, 18),
        unicamp_stage_2_date=date(2026, 11, 29)
    )
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir(parents=True, exist_ok=True)
    track_mgr = TrackManager(settings=settings, tracks_dir=tracks_dir)

    # Cria trilha padrão no ambiente temporário
    t1 = StudyTrack(
        id="unicamp_cc",
        name="Vestibular Unicamp",
        description="Foco Unicamp",
        target_date="2026-10-18",
        subjects=DEFAULT_SUBJECTS,
        is_active=True
    )
    track_mgr.create_track(t1)

    state_mgr = StateManager(settings)
    metrics = MetricsEngine(settings=settings, state_manager=state_mgr, track_manager=track_mgr)
    return settings, state_mgr, track_mgr, metrics


def test_daily_metrics_and_accuracy_calculation(test_environment):
    """Testa cálculo de métricas diárias e precisão com múltiplos logs e trilhas."""
    settings, state_mgr, track_mgr, metrics = test_environment
    today_str = date.today().strftime("%Y-%m-%d")

    # Adiciona 2 logs no dia
    log1 = StudyLog(
        id="l1",
        track_id="unicamp_cc",
        date=today_str,
        subject="Matemática",
        correct_answers=8,
        total_questions=10,
        accuracy_rate=0.8,
        minutes_spent=50,
        deliverable_completed=True
    )
    log2 = StudyLog(
        id="l2",
        track_id="unicamp_cc",
        date=today_str,
        subject="Física",
        correct_answers=6,
        total_questions=10,
        accuracy_rate=0.6,
        minutes_spent=50,
        deliverable_completed=True
    )

    state_mgr.add_log(log1)
    state_mgr.add_log(log2)

    daily = metrics.get_daily_metrics()

    assert daily["total_questions"] == 20
    assert daily["correct_answers"] == 14
    assert daily["overall_accuracy"] == 0.7
    assert daily["minutes_spent"] == 100
    assert daily["deliverables_completed"] == 2
    assert "matemática" in daily["by_subject"]
    assert daily["by_subject"]["matemática"]["accuracy"] == 0.8
    assert "unicamp_cc" in daily["by_track"]
    assert daily["by_track"]["unicamp_cc"]["questions"] == 20


def test_daily_report_generation(test_environment):
    """Testa exportação de relatório diário em JSON e Markdown."""
    settings, state_mgr, track_mgr, metrics = test_environment
    today_str = date.today().strftime("%Y-%m-%d")

    log = StudyLog(
        id="l_rep",
        track_id="unicamp_cc",
        date=today_str,
        subject="Química",
        correct_answers=9,
        total_questions=10,
        accuracy_rate=0.9,
        minutes_spent=45,
        deliverable_completed=True,
        deliverable_description="Balanceamento de reações redox"
    )
    state_mgr.add_log(log)

    json_path, md_path = metrics.generate_daily_report()

    assert json_path.exists(), "Arquivo JSON do relatório deve ser criado"
    assert md_path.exists(), "Arquivo Markdown do relatório deve ser criado"

    # Valida integridade do JSON
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["total_questions"] == 10
    assert data["correct_answers"] == 9

    # Valida conteúdo do Markdown
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()
    assert "Química" in md_content
    assert "90.0%" in md_content


def test_weekly_metrics_and_report(test_environment):
    """Testa agregação semanal de progresso frente às metas de trilhas."""
    settings, state_mgr, track_mgr, metrics = test_environment
    today_str = date.today().strftime("%Y-%m-%d")

    log = StudyLog(
        id="l_week",
        track_id="unicamp_cc",
        date=today_str,
        subject="Matemática",
        correct_answers=15,
        total_questions=20,
        accuracy_rate=0.75,
        minutes_spent=90,
        deliverable_completed=True
    )
    state_mgr.add_log(log)

    weekly = metrics.get_weekly_metrics()

    assert weekly["total_questions"] == 20
    assert "tracks" in weekly
    assert "unicamp_cc" in weekly["tracks"]
    assert weekly["tracks"]["unicamp_cc"]["days_remaining"] is not None

    json_path, md_path = metrics.generate_weekly_report()
    assert json_path.exists()
    assert md_path.exists()

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Relatório Semanal OrientAI" in content
    assert "Vestibular Unicamp" in content
    assert "Matemática" in content
