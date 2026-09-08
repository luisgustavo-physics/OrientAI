"""Testes unitários para o agendador de estudos multi-trilhas (core/scheduler.py)."""

from datetime import date, datetime
import pytest

from config.settings import FixedCommitment, Settings
from config.subjects import DEFAULT_SUBJECTS, Subject
from core.models import ActivityType, AppState, StudyBlock, StudyTrack, SubjectConfig, SubjectProgress
from core.scheduler import StudyScheduler
from core.state import StateManager
from core.tracks import TrackManager


@pytest.fixture
def test_settings(tmp_path):
    """Configurações isoladas com diretório temporário para testes."""
    return Settings(
        data_dir=tmp_path / "data",
        daily_study_hours=4.0,
        pomodoro_work_minutes=50,
        pomodoro_break_minutes=10,
        anki_review_minutes=15,
        day_start_hour=8,
        day_end_hour=20,
        routine_commitments=[
            FixedCommitment(title="Almoço", start="12:00", end="13:00"),
            FixedCommitment(title="Treino", start="17:00", end="18:00")
        ]
    )


@pytest.fixture
def scheduler(test_settings, tmp_path):
    """Instância do scheduler com estado e trilhas isolados."""
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir(parents=True, exist_ok=True)
    track_mgr = TrackManager(test_settings, tracks_dir=tracks_dir)

    # Cria trilha de teste
    t1 = StudyTrack(
        id="unicamp_cc",
        name="Vestibular Unicamp",
        description="Foco Unicamp",
        target_date="2026-10-18",
        subjects=DEFAULT_SUBJECTS,
        is_active=True
    )
    t2 = StudyTrack(
        id="faculdade_computacao",
        name="Ciência da Computação Semestre",
        description="Foco Universitário",
        target_date="2026-12-15",
        subjects={
            "algoritmos_ed": SubjectConfig(
                id="algoritmos_ed",
                name="Estruturas de Dados",
                subject_type="computacao",
                weight=3.0,
                weekly_questions_goal=10,
                requires_tangible_deliverable=True,
                deliverable_templates=["Implementar árvore balanceada com testes"]
            )
        },
        is_active=True
    )
    track_mgr.create_track(t1)
    track_mgr.create_track(t2)

    state_mgr = StateManager(test_settings)
    return StudyScheduler(
        settings=test_settings,
        state_manager=state_mgr,
        track_manager=track_mgr
    )


def test_priority_calculation_weights_and_gaps(scheduler):
    """Testa se matérias com peso maior e menor acurácia ganham prioridade mais alta."""
    today = date(2026, 9, 7)
    math_conf = DEFAULT_SUBJECTS[Subject.MATEMATICA.value]  # peso 3.0
    english_conf = DEFAULT_SUBJECTS[Subject.INGLES.value]   # peso 1.0

    # Matemática com gap de 50% de acertos
    math_prog = SubjectProgress(
        subject="Matemática",
        track_id="unicamp_cc",
        total_questions_solved=20,
        total_questions_correct=10,
        accuracy_rate=0.5,
        last_studied_date="2026-09-01"
    )

    # Inglês com 95% de acertos
    eng_prog = SubjectProgress(
        subject="Inglês",
        track_id="unicamp_cc",
        total_questions_solved=20,
        total_questions_correct=19,
        accuracy_rate=0.95,
        last_studied_date="2026-09-06"
    )

    score_math = scheduler.calculate_subject_priority(math_conf, math_prog, today)
    score_eng = scheduler.calculate_subject_priority(english_conf, eng_prog, today)

    assert score_math > score_eng, "Matemática com gap deve ter score maior que Inglês com alta acurácia"


def test_anti_passivity_rule_for_stem(scheduler):
    """Testa que blocos de matérias de Exatas e Computação OBRIGATORIAMENTE têm entregáveis tangíveis."""
    plan = scheduler.generate_daily_plan(target_date=date(2026, 9, 7))

    assert len(plan.blocks) > 0, "O plano deve conter blocos gerados"

    for block in plan.blocks:
        assert block.track_id is not None and len(block.track_id) > 0
        if block.subject_id in (Subject.MATEMATICA.value, Subject.FISICA.value, Subject.QUIMICA.value, Subject.COMPUTACAO.value, "algoritmos_ed"):
            if block.activity_type != ActivityType.ANKI_REVISAO:
                assert block.requires_tangible is True, f"Bloco {block.id} ({block.subject_name}) deve exigir entregável tangível"
                assert len(block.deliverable.strip()) > 10, "O entregável não pode ser vazio ou genérico"
                lower_deliv = block.deliverable.lower()
                assert "assistir" not in lower_deliv
                assert "apenas ler" not in lower_deliv


def test_schedule_specific_track_filtering(scheduler):
    """Testa geração de plano focado exclusivamente em uma única trilha solicitada."""
    plan = scheduler.generate_daily_plan(target_date=date(2026, 9, 7), track_id="faculdade_computacao")

    assert len(plan.blocks) > 0
    assert plan.active_tracks == ["faculdade_computacao"]
    for block in plan.blocks:
        assert block.track_id == "faculdade_computacao"
        assert block.subject_id == "algoritmos_ed"


def test_no_overlap_with_routine_commitments(scheduler, test_settings):
    """Garante que nenhum bloco de estudo sobrepõe compromissos fixos da rotina."""
    test_date = date(2026, 9, 7)
    plan = scheduler.generate_daily_plan(target_date=test_date)

    commitments = [
        (datetime.strptime("12:00", "%H:%M").time(), datetime.strptime("13:00", "%H:%M").time()),
        (datetime.strptime("17:00", "%H:%M").time(), datetime.strptime("18:00", "%H:%M").time())
    ]

    for block in plan.blocks:
        b_start = datetime.strptime(block.start_time, "%H:%M").time()
        b_end = datetime.strptime(block.end_time, "%H:%M").time()

        for c_start, c_end in commitments:
            overlap = (b_start < c_end) and (b_end > c_start)
            assert not overlap, f"Bloco {block.id} ({block.start_time}-{block.end_time}) colide com compromisso ({c_start}-{c_end})"


def test_consecutive_subject_limit(scheduler):
    """Testa que nenhuma matéria é alocada por mais de 2 blocos consecutivos."""
    plan = scheduler.generate_daily_plan(target_date=date(2026, 9, 7))

    consecutive_count = 0
    last_subject = None

    for block in plan.blocks:
        if block.activity_type == ActivityType.ANKI_REVISAO:
            continue

        if block.subject_id == last_subject:
            consecutive_count += 1
            assert consecutive_count <= 2, f"Matéria {block.subject_name} teve mais de 2 blocos consecutivos"
        else:
            consecutive_count = 1
            last_subject = block.subject_id
