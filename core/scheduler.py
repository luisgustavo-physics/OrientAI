"""Algoritmo de agendamento inteligente, agnóstico e adaptativo para múltiplas trilhas de estudo e DAG."""

from datetime import date, datetime, time, timedelta
import random
from typing import Any, Dict, List, Optional, Tuple

from config.settings import FixedCommitment, Settings, get_settings
from core.graph_engine import GraphEngine
from core.models import ActivityType, AppState, DailyPlan, StudyBlock, StudyTrack, SubjectConfig, SubjectProgress, TopicNode
from core.state import StateManager
from core.tracks import TrackManager
from integrations.anki_sync import AnkiClient


class StudyScheduler:
    """Gera planos de estudo diários otimizados e balanceados entre trilhas de estudo e grafos DAG."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        state_manager: Optional[StateManager] = None,
        anki_client: Optional[AnkiClient] = None,
        track_manager: Optional[TrackManager] = None
    ):
        self.settings = settings or get_settings()
        self.state_manager = state_manager or StateManager(self.settings)
        self.anki_client = anki_client or AnkiClient(self.settings)
        self.track_manager = track_manager or TrackManager(self.settings)

    def calculate_subject_priority(
        self,
        subject_conf: SubjectConfig,
        progress: Optional[SubjectProgress],
        today: date,
        pending_anki_cards: int = 0
    ) -> float:
        """Calcula o score de prioridade de uma matéria com base em gaps, peso e recência."""
        weight_factor = max(0.5, subject_conf.weight)

        if progress is None or progress.total_questions_solved == 0:
            accuracy_gap = 0.5
        else:
            accuracy_gap = max(0.1, 1.0 - progress.accuracy_rate)

        days_since_last = 7
        if progress and progress.last_studied_date:
            try:
                last_date = datetime.strptime(progress.last_studied_date, "%Y-%m-%d").date()
                days_since_last = max(1, (today - last_date).days)
            except ValueError:
                days_since_last = 5
        recency_factor = min(3.0, 1.0 + (days_since_last * 0.25))
        anki_bonus = 1.0 + (min(pending_anki_cards, 50) / 100.0)

        score = (weight_factor * 1.5) * (accuracy_gap * 2.0) * recency_factor * anki_bonus
        return round(score, 3)

    def _get_time_slots(
        self,
        target_date: date,
        commitments: List[FixedCommitment]
    ) -> List[Tuple[datetime, datetime]]:
        """Gera intervalos de tempo livres disponíveis para estudo no dia."""
        weekday = target_date.weekday()
        day_commitments: List[Tuple[datetime, datetime, str]] = []
        for c in commitments:
            if weekday in c.days_of_week:
                st = datetime.combine(target_date, c.start_time())
                et = datetime.combine(target_date, c.end_time())
                day_commitments.append((st, et, c.title))

        day_commitments.sort(key=lambda x: x[0])

        cursor = datetime.combine(target_date, time(hour=self.settings.day_start_hour, minute=0))
        day_end = datetime.combine(target_date, time(hour=self.settings.day_end_hour, minute=0))

        free_slots: List[Tuple[datetime, datetime]] = []

        for c_start, c_end, _ in day_commitments:
            if c_start > cursor:
                slot_end = min(c_start, day_end)
                if (slot_end - cursor).total_seconds() >= 15 * 60:
                    free_slots.append((cursor, slot_end))
            cursor = max(cursor, c_end)
            if cursor >= day_end:
                break

        if cursor < day_end:
            free_slots.append((cursor, day_end))

        return free_slots

    def _generate_deliverable(
        self,
        track: StudyTrack,
        subject_conf: SubjectConfig,
        activity_type: ActivityType
    ) -> Tuple[str, bool]:
        """Gera um entregável tangível contextualizado para a disciplina e trilha."""
        sub_type = subject_conf.subject_type.lower()
        requires_tangible = (
            subject_conf.requires_tangible_deliverable or
            sub_type in ("exatas", "computacao", "tecnologia") or
            activity_type in (ActivityType.IMPLEMENTACAO, ActivityType.DISCURSIVA, ActivityType.PROJETO)
        )

        if activity_type == ActivityType.ANKI_REVISAO:
            deck = subject_conf.anki_deck or track.name
            return (
                f"Zerar revisões pendentes do deck '{deck}' mantendo retenção >= 85%",
                False
            )
        elif activity_type == ActivityType.IMPLEMENTACAO:
            return (
                f"Implementar código/algoritmo em Python/C++ com testes unitários para {subject_conf.name}",
                True
            )
        elif activity_type == ActivityType.DISCURSIVA:
            return (
                f"Redigir 4 respostas detalhadas em folha padrão/markdown sobre tópicos centrais de {subject_conf.name}",
                True
            )
        elif activity_type == ActivityType.PROJETO:
            return (
                f"Desenvolver etapa tangível do projeto prático em {subject_conf.name} com commit e documentação",
                True
            )
        else:
            if subject_conf.deliverable_templates:
                template = random.choice(subject_conf.deliverable_templates)
                return template, requires_tangible
            elif sub_type in ("exatas", "computacao"):
                return (
                    f"Resolver lista de 8 exercícios práticos de {subject_conf.name} anotando taxa de acerto",
                    True
                )
            else:
                return (
                    f"Resolver lista de 6 questões práticas de {subject_conf.name} com mapa mental dos erros",
                    requires_tangible
                )

    def generate_daily_plan(
        self,
        target_date: Optional[date] = None,
        track_id: Optional[str] = None
    ) -> DailyPlan:
        """Gera o plano diário balanceando trilhas ativas ou focando em uma trilha específica."""
        today = target_date or date.today()
        state = self.state_manager.load_state()

        # 1. Determina quais trilhas serão agendadas
        if track_id:
            selected_track = self.track_manager.get_track(track_id)
            if not selected_track:
                raise ValueError(f"Trilha '{track_id}' não foi encontrada.")
            tracks_to_schedule = [selected_track]
        else:
            tracks_to_schedule = self.track_manager.get_active_tracks()
            if not tracks_to_schedule:
                all_tracks = list(self.track_manager.load_all_tracks().values())
                if all_tracks:
                    tracks_to_schedule = all_tracks
                else:
                    from config.subjects import DEFAULT_SUBJECTS
                    default_track = StudyTrack(
                        id="comvest",
                        name="Vestibular Unicamp",
                        description="Trilha Padrão",
                        subjects=DEFAULT_SUBJECTS
                    )
                    tracks_to_schedule = [default_track]

        # 2. Checa status do Anki
        anki_stats = self.anki_client.get_today_stats()
        anki_pending_by_deck = anki_stats.get("decks_pending", {})
        total_anki_pending = anki_stats.get("total_pending", 0)

        # 3. Calcula prioridades respeitando tópicos liberados no grafo DAG
        priorities: List[Tuple[float, StudyTrack, Any]] = []
        for track in tracks_to_schedule:
            if track.nodes:
                GraphEngine.initialize_track_graph(track)
                available_nodes = GraphEngine.get_available_topics(track)
                for node in available_nodes:
                    sub_conf = track.get_subject(node.subject)
                    weight = sub_conf.weight if sub_conf else 2.0
                    acc_gap = max(0.1, 1.0 - node.current_accuracy) if node.total_questions > 0 else 0.5
                    score = round(weight * 1.5 * acc_gap * 2.0, 3)
                    priorities.append((score, track, node))
            else:
                for sub_id, conf in track.subjects.items():
                    prog = self.state_manager.get_subject_progress(conf.id, track_id=track.id)
                    deck_pending = anki_pending_by_deck.get(conf.anki_deck, 0) if conf.anki_deck else 0
                    score = self.calculate_subject_priority(conf, prog, today, deck_pending)
                    priorities.append((score, track, conf))

        priorities.sort(key=lambda x: x[0], reverse=True)
        if not priorities:
            raise ValueError("Nenhuma matéria ou tópico liberado para estudo nas trilhas selecionadas.")

        # 4. Calcula horários livres no dia
        free_slots = self._get_time_slots(today, self.settings.routine_commitments)

        # 5. Alocação de blocos
        allocated_blocks: List[StudyBlock] = []
        target_minutes = int(self.settings.daily_study_hours * 60)
        accumulated_minutes = 0
        block_counter = 1

        subject_index = 0
        last_allocated_id: Optional[str] = None
        consecutive_count = 0

        anki_allocated = False
        anki_block_mins = self.settings.anki_review_minutes
        pomodoro_mins = self.settings.pomodoro_work_minutes
        break_mins = self.settings.pomodoro_break_minutes

        for slot_start, slot_end in free_slots:
            slot_cursor = slot_start

            while slot_cursor + timedelta(minutes=anki_block_mins) <= slot_end and accumulated_minutes < target_minutes:
                # Aloca bloco de Anki se ainda não alocou e há pendências
                if total_anki_pending > 0 and not anki_allocated:
                    b_end = slot_cursor + timedelta(minutes=anki_block_mins)
                    top_track = priorities[0][1]
                    top_item = priorities[0][2]
                    
                    block = StudyBlock(
                        id=f"B{block_counter:02d}",
                        track_id=top_track.id,
                        subject_id="anki_geral",
                        subject_name=f"Revisão Ativa Anki ({top_track.name})",
                        activity_type=ActivityType.ANKI_REVISAO,
                        start_time=slot_cursor.strftime("%H:%M"),
                        end_time=b_end.strftime("%H:%M"),
                        duration_minutes=anki_block_mins,
                        deliverable=f"Revisar {min(total_anki_pending, 30)} flashcards prioritários do dia",
                        requires_tangible=False
                    )
                    allocated_blocks.append(block)
                    accumulated_minutes += anki_block_mins
                    slot_cursor = b_end + timedelta(minutes=5)
                    block_counter += 1
                    anki_allocated = True
                    continue

                if slot_cursor + timedelta(minutes=pomodoro_mins) > slot_end:
                    break

                chosen = priorities[subject_index % len(priorities)]
                candidate_track = chosen[1]
                candidate_item = chosen[2]

                item_id = candidate_item.id if hasattr(candidate_item, "id") else str(candidate_item)
                if item_id == last_allocated_id and consecutive_count >= 2:
                    subject_index += 1
                    chosen = priorities[subject_index % len(priorities)]
                    candidate_track = chosen[1]
                    candidate_item = chosen[2]
                    item_id = candidate_item.id if hasattr(candidate_item, "id") else str(candidate_item)

                if item_id == last_allocated_id:
                    consecutive_count += 1
                else:
                    consecutive_count = 1
                    last_allocated_id = item_id

                # Diferencia se o item é um nó de grafo (TopicNode) ou configuração flat (SubjectConfig)
                if isinstance(candidate_item, TopicNode):
                    node: TopicNode = candidate_item
                    sub_id = node.id
                    sub_name = f"{node.name} ({node.subject})"
                    topic_id = node.id
                    act_type = ActivityType.IMPLEMENTACAO if any(w in (node.name + node.subject).lower() for w in ["computa", "algoritmo", "codigo", "ia"]) else ActivityType.QUESTOES
                    deliverable = node.deliverable_template or f"Resolver lista prática de 8 exercícios de {node.name}"
                    if node.notebook_ref:
                        deliverable += f" [Ref: {node.notebook_ref}]"
                    req_tangible = True
                else:
                    conf: SubjectConfig = candidate_item
                    sub_id = conf.id
                    sub_name = conf.name
                    topic_id = None
                    sub_type = conf.subject_type.lower()
                    if sub_type in ("computacao", "tecnologia"):
                        act_type = ActivityType.IMPLEMENTACAO
                    elif sub_type == "exatas":
                        act_type = ActivityType.DISCURSIVA if (block_counter % 2 == 0) else ActivityType.QUESTOES
                    else:
                        act_type = ActivityType.QUESTOES
                    deliverable, req_tangible = self._generate_deliverable(candidate_track, conf, act_type)

                b_end = slot_cursor + timedelta(minutes=pomodoro_mins)
                block = StudyBlock(
                    id=f"B{block_counter:02d}",
                    track_id=candidate_track.id,
                    subject_id=sub_id,
                    subject_name=sub_name,
                    topic_id=topic_id,
                    activity_type=act_type,
                    start_time=slot_cursor.strftime("%H:%M"),
                    end_time=b_end.strftime("%H:%M"),
                    duration_minutes=pomodoro_mins,
                    deliverable=deliverable,
                    requires_tangible=req_tangible
                )
                allocated_blocks.append(block)
                accumulated_minutes += pomodoro_mins
                block_counter += 1

                slot_cursor = b_end + timedelta(minutes=break_mins)
                subject_index += 1

        tracks_names = [t.name for t in tracks_to_schedule]
        top_subjects_names = [
            f"{item.name} ({track.name})" for _, track, item in priorities[:3]
        ]
        focus_summary = (
            f"Trilhas ativas: {', '.join(tracks_names)}. "
            f"Foco prioritário em: {', '.join(top_subjects_names)}. "
            f"Total de {len(allocated_blocks)} blocos de ação com entregáveis verificáveis."
        )

        commitments_summary = [f"{c.title} ({c.start}-{c.end})" for c in self.settings.routine_commitments]

        plan = DailyPlan(
            date=today.strftime("%Y-%m-%d"),
            blocks=allocated_blocks,
            total_planned_minutes=accumulated_minutes,
            commitments_accounted=commitments_summary,
            anki_pending_cards=total_anki_pending,
            focus_summary=focus_summary,
            active_tracks=[t.id for t in tracks_to_schedule]
        )

        self.state_manager.set_active_plan(plan)
        return plan
