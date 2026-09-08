"""Métricas de progresso, análise de retenção e gerador de relatórios por trilha de estudo."""

from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import Settings, get_settings
from core.models import AppState, DailyPlan, StudyLog, StudyTrack
from core.state import StateManager
from core.tracks import TrackManager
from integrations.anki_sync import AnkiClient


class MetricsEngine:
    """Calcula indicadores de desempenho e exporta relatórios analíticos multi-trilhas."""

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

    def get_subject_accuracy(self, state: Optional[AppState] = None) -> Dict[str, float]:
        """Retorna taxa de acerto consolidada por matéria."""
        state = state or self.state_manager.load_state()
        result: Dict[str, float] = {}
        for sub_id, prog in state.subjects.items():
            result[sub_id] = prog.accuracy_rate
        return result

    def get_daily_metrics(
        self,
        target_date: Optional[date] = None,
        track_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calcula métricas agregadas do dia, com divisão por trilha."""
        ref_date = target_date or date.today()
        ref_str = ref_date.strftime("%Y-%m-%d")
        state = self.state_manager.load_state()

        # Logs do dia (opcionalmente filtrados por trilha)
        day_logs = [log for log in state.logs if log.date == ref_str]
        if track_id:
            day_logs = [log for log in day_logs if log.track_id == track_id]

        # Plano do dia
        active_plan = self.state_manager.get_active_plan(ref_str)
        planned_minutes = active_plan.total_planned_minutes if active_plan else int(self.settings.daily_study_hours * 60)

        total_questions = sum(log.total_questions for log in day_logs)
        correct_answers = sum(log.correct_answers for log in day_logs)
        minutes_spent = sum(log.minutes_spent for log in day_logs)
        deliverables_done = sum(1 for log in day_logs if log.deliverable_completed)

        overall_accuracy = round(correct_answers / total_questions, 4) if total_questions > 0 else 0.0
        time_adherence = round((minutes_spent / planned_minutes) * 100, 1) if planned_minutes > 0 else 0.0

        # Anki
        anki_stats = self.anki_client.get_today_stats()

        # Detalhamento por trilha e por matéria
        by_track: Dict[str, Dict[str, Any]] = {}
        by_subject: Dict[str, Dict[str, Any]] = {}

        for log in day_logs:
            t_id = log.track_id or "geral"
            sub = log.subject.lower()

            # Agregação por trilha
            if t_id not in by_track:
                by_track[t_id] = {
                    "questions": 0,
                    "correct": 0,
                    "minutes": 0,
                    "sessions": 0,
                    "subjects": {}
                }
            by_track[t_id]["questions"] += log.total_questions
            by_track[t_id]["correct"] += log.correct_answers
            by_track[t_id]["minutes"] += log.minutes_spent
            by_track[t_id]["sessions"] += 1

            # Agregação por matéria dentro da trilha
            if sub not in by_track[t_id]["subjects"]:
                by_track[t_id]["subjects"][sub] = {"questions": 0, "correct": 0, "minutes": 0}
            by_track[t_id]["subjects"][sub]["questions"] += log.total_questions
            by_track[t_id]["subjects"][sub]["correct"] += log.correct_answers
            by_track[t_id]["subjects"][sub]["minutes"] += log.minutes_spent

            # Agregação flat por matéria (para compatibilidade)
            if sub not in by_subject:
                by_subject[sub] = {"questions": 0, "correct": 0, "minutes": 0, "sessions": 0}
            by_subject[sub]["questions"] += log.total_questions
            by_subject[sub]["correct"] += log.correct_answers
            by_subject[sub]["minutes"] += log.minutes_spent
            by_subject[sub]["sessions"] += 1

        for sub, data in by_subject.items():
            q = data["questions"]
            c = data["correct"]
            data["accuracy"] = round(c / q, 4) if q > 0 else 0.0

        for t_id, data in by_track.items():
            q = data["questions"]
            c = data["correct"]
            data["accuracy"] = round(c / q, 4) if q > 0 else 0.0

        return {
            "date": ref_str,
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "overall_accuracy": overall_accuracy,
            "minutes_spent": minutes_spent,
            "planned_minutes": planned_minutes,
            "time_adherence_percent": time_adherence,
            "deliverables_completed": deliverables_done,
            "total_logs": len(day_logs),
            "anki_cards_reviewed": anki_stats.get("reviewed_today", 0),
            "anki_pending_cards": anki_stats.get("total_pending", 0),
            "by_track": by_track,
            "by_subject": by_subject
        }

    def generate_daily_report(self, target_date: Optional[date] = None) -> Tuple[Path, Path]:
        """Gera e salva relatórios diários em JSON e Markdown."""
        metrics = self.get_daily_metrics(target_date)
        ref_str = metrics["date"]
        logs_dir = self.settings.logs_dir

        # 1. Salva JSON
        json_path = logs_dir / f"daily_{ref_str}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)

        # 2. Gera Markdown
        md_lines = [
            f"# Relatório Diário de Estudos - {ref_str}",
            "",
            "## Resumo Executivo",
            f"- **Tempo Dedicado:** {metrics['minutes_spent']} min / {metrics['planned_minutes']} min planejados ({metrics['time_adherence_percent']}% de aderência)",
            f"- **Exercícios/Tarefas:** {metrics['total_questions']} (Acertos: {metrics['correct_answers']})",
            f"- **Taxa de Acerto Geral:** {metrics['overall_accuracy'] * 100:.1f}%",
            f"- **Entregáveis Tangíveis Cumpridos:** {metrics['deliverables_completed']} de {metrics['total_logs']} sessões",
            f"- **Cards Revisados no Anki:** {metrics['anki_cards_reviewed']}",
            "",
            "## Desempenho por Matéria",
            "| Matéria | Exercícios | Acertos | Taxa Acerto | Tempo (min) |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]

        if metrics["by_subject"]:
            for sub, d in metrics["by_subject"].items():
                acc_pct = f"{d['accuracy'] * 100:.1f}%"
                md_lines.append(f"| {sub.title()} | {d['questions']} | {d['correct']} | {acc_pct} | {d['minutes']} |")
        else:
            md_lines.append("| *Nenhum log registrado para esta data* | - | - | - | - |")

        md_lines.extend([
            "",
            "## Checklist Anti-Passividade",
            f"- [x] Entregáveis com resolução discursiva ou código: {'SIM' if metrics['deliverables_completed'] > 0 else 'NÃO'}",
            f"- [x] Sessões sem passividade auditiva: {'OK' if metrics['total_questions'] > 0 else 'ALERTA: Nenhuma questão prática registrada!'}",
            ""
        ])

        md_path = logs_dir / f"daily_{ref_str}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return json_path, md_path

    def get_weekly_metrics(self, end_date: Optional[date] = None) -> Dict[str, Any]:
        """Calcula métricas da semana (últimos 7 dias) decompostas por trilha."""
        ref_end = end_date or date.today()
        ref_start = ref_end - timedelta(days=6)
        state = self.state_manager.load_state()

        week_logs = []
        for log in state.logs:
            try:
                log_dt = datetime.strptime(log.date, "%Y-%m-%d").date()
                if ref_start <= log_dt <= ref_end:
                    week_logs.append(log)
            except ValueError:
                continue

        total_questions = sum(log.total_questions for log in week_logs)
        correct_answers = sum(log.correct_answers for log in week_logs)
        minutes_spent = sum(log.minutes_spent for log in week_logs)
        overall_accuracy = round(correct_answers / total_questions, 4) if total_questions > 0 else 0.0

        # Carrega trilhas
        all_tracks = self.track_manager.load_all_tracks()
        tracks_data: Dict[str, Dict[str, Any]] = {}
        flat_subjects: Dict[str, Dict[str, Any]] = {}

        for track_id, track in all_tracks.items():
            days_left = None
            if track.target_date:
                try:
                    t_date = datetime.strptime(track.target_date, "%Y-%m-%d").date()
                    days_left = (t_date - ref_end).days
                except ValueError:
                    pass

            track_subjects_stats: Dict[str, Dict[str, Any]] = {}
            for sub_id, conf in track.subjects.items():
                sub_logs = [
                    l for l in week_logs
                    if (l.track_id == track_id or not l.track_id) and
                    (l.subject.lower() in (sub_id, conf.name.lower()))
                ]
                q = sum(l.total_questions for l in sub_logs)
                c = sum(l.correct_answers for l in sub_logs)
                m = sum(l.minutes_spent for l in sub_logs)
                acc = round(c / q, 4) if q > 0 else 0.0
                goal = conf.weekly_questions_goal
                progress_pct = round((q / goal) * 100, 1) if goal > 0 else 0.0

                sub_data = {
                    "name": conf.name,
                    "weight": conf.weight,
                    "questions_solved": q,
                    "goal": goal,
                    "goal_progress_percent": progress_pct,
                    "correct_answers": c,
                    "accuracy": acc,
                    "minutes_spent": m
                }
                track_subjects_stats[sub_id] = sub_data
                flat_subjects[f"{track_id}:{sub_id}"] = sub_data
                # Fallback chave simples
                if sub_id not in flat_subjects:
                    flat_subjects[sub_id] = sub_data

            tracks_data[track_id] = {
                "name": track.name,
                "is_active": track.is_active,
                "target_date": track.target_date,
                "days_remaining": days_left,
                "subjects": track_subjects_stats
            }

        # Dias até prova Unicamp se configurado
        days_to_stage_1 = (self.settings.unicamp_stage_1_date - ref_end).days
        days_to_stage_2 = (self.settings.unicamp_stage_2_date - ref_end).days

        return {
            "week_start": ref_start.strftime("%Y-%m-%d"),
            "week_end": ref_end.strftime("%Y-%m-%d"),
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "overall_accuracy": overall_accuracy,
            "total_hours_studied": round(minutes_spent / 60, 1),
            "days_to_stage_1": days_to_stage_1,
            "days_to_stage_2": days_to_stage_2,
            "tracks": tracks_data,
            "subjects": flat_subjects
        }

    def generate_weekly_report(self, end_date: Optional[date] = None) -> Tuple[Path, Path]:
        """Gera relatório semanal comparativo em JSON e Markdown."""
        metrics = self.get_weekly_metrics(end_date)
        week_tag = f"{metrics['week_start']}_to_{metrics['week_end']}"
        logs_dir = self.settings.logs_dir

        json_path = logs_dir / f"weekly_{week_tag}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)

        md_lines = [
            f"# Relatório Semanal OrientAI ({metrics['week_start']} até {metrics['week_end']})",
            "",
            "## Desempenho Global da Semana",
            f"- **Horas Totais:** {metrics['total_hours_studied']}h",
            f"- **Exercícios Resolvidos:** {metrics['total_questions']} (Taxa Geral: {metrics['overall_accuracy'] * 100:.1f}%)",
            ""
        ]

        # Seção por trilha
        for track_id, track_data in metrics.get("tracks", {}).items():
            if not track_data["is_active"]:
                continue
            
            target_str = f" | Prazo Alvo: {track_data['days_remaining']} dias restantes" if track_data.get("days_remaining") is not None else ""
            md_lines.extend([
                f"### Trilha: {track_data['name']}{target_str}",
                "",
                "| Disciplina | Peso | Progresso Semanal | % Meta | Acurácia | Horas |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |"
            ])

            for _, d in track_data["subjects"].items():
                acc = f"{d['accuracy'] * 100:.1f}%" if d['questions_solved'] > 0 else "N/A"
                hrs = f"{d['minutes_spent'] / 60:.1f}h"
                md_lines.append(
                    f"| {d['name']} | {d['weight']}x | {d['questions_solved']} / {d['goal']} | {d['goal_progress_percent']}% | {acc} | {hrs} |"
                )
            md_lines.append("")

        md_path = logs_dir / f"weekly_{week_tag}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return json_path, md_path
