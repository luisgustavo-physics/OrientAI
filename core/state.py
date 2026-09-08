"""Gerenciador de persistência do estado da aplicação em JSON local com suporte a trilhas."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import Settings, get_settings
from core.models import AppState, DailyPlan, StudyLog, SubjectProgress


class StateManager:
    """Gerencia leitura e escrita do estado persistente do OrientAI."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.state_file: Path = self.settings.state_file

    def _create_initial_state(self) -> AppState:
        """Cria o estado inicial pré-populado."""
        from config.subjects import DEFAULT_SUBJECTS
        initial_subjects = {}
        for key, conf in DEFAULT_SUBJECTS.items():
            initial_subjects[key] = SubjectProgress(
                subject=conf.name,
                track_id="unicamp_cc",
                total_questions_solved=0,
                total_questions_correct=0,
                accuracy_rate=0.0,
                total_minutes_studied=0,
                last_studied_date=None,
                anki_cards_reviewed=0,
                sessions_count=0
            )
        now_str = datetime.now().isoformat()
        state = AppState(
            created_at=now_str,
            updated_at=now_str,
            subjects=initial_subjects,
            logs=[],
            active_plan=None
        )
        self.save_state(state)
        return state

    def load_state(self) -> AppState:
        """Carrega o estado do arquivo JSON ou inicializa um novo se não existir."""
        if not self.state_file.exists():
            return self._create_initial_state()

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = AppState.model_validate(data)
            
            # Garante que logs legados tenham track_id padrão
            changed = False
            for log in state.logs:
                if not hasattr(log, "track_id") or not log.track_id:
                    log.track_id = "unicamp_cc"
                    changed = True

            if changed:
                self.save_state(state)
                
            return state
        except Exception as e:
            # Em caso de arquivo corrompido, cria backup e reinicializa
            backup_file = self.state_file.with_suffix(f".bak.{int(datetime.now().timestamp())}")
            if self.state_file.exists():
                self.state_file.rename(backup_file)
            return self._create_initial_state()

    def save_state(self, state: AppState) -> None:
        """Salva o estado atualizado no arquivo JSON de forma segura."""
        state.updated_at = datetime.now().isoformat()
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Escrita atômica via arquivo temporário
        temp_file = self.state_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(), f, indent=2, ensure_ascii=False)
        temp_file.replace(self.state_file)

    def add_log(self, log: StudyLog) -> AppState:
        """Registra uma sessão de estudo e atualiza o progresso da matéria."""
        state = self.load_state()
        state.logs.append(log)

        # Encontra a chave da matéria correspondente
        track_id = log.track_id or "unicamp_cc"
        subject_input = log.subject.lower().strip()
        
        # Procura por chave exata ou composta (track_id:subject)
        candidates = [
            f"{track_id}:{subject_input}",
            subject_input
        ]
        
        matched_key = None
        for cand in candidates:
            if cand in state.subjects:
                matched_key = cand
                break

        # Se não achou, busca por nome dentro da mesma trilha
        if not matched_key:
            for key, prog in state.subjects.items():
                if prog.subject.lower() == subject_input and (prog.track_id == track_id or prog.track_id is None):
                    matched_key = key
                    break

        # Se ainda não achou, cria nova entrada indexada
        if not matched_key:
            matched_key = f"{track_id}:{subject_input}"
            state.subjects[matched_key] = SubjectProgress(
                subject=log.subject,
                track_id=track_id
            )

        state.subjects[matched_key].track_id = track_id
        state.subjects[matched_key].update_with_log(log)
        self.save_state(state)
        return state

    def get_subject_progress(self, subject: str, track_id: Optional[str] = None) -> Optional[SubjectProgress]:
        """Recupera progresso de uma matéria, opcionalmente filtrada por trilha."""
        state = self.load_state()
        sub_lower = subject.lower().strip()
        
        # Prioriza match com track_id
        if track_id:
            composite = f"{track_id}:{sub_lower}"
            if composite in state.subjects:
                return state.subjects[composite]
            for prog in state.subjects.values():
                if prog.subject.lower() == sub_lower and prog.track_id == track_id:
                    return prog

        if sub_lower in state.subjects:
            return state.subjects[sub_lower]

        for prog in state.subjects.values():
            if prog.subject.lower() == sub_lower:
                return prog
        return None

    def set_active_plan(self, plan: DailyPlan) -> None:
        """Salva o plano diário ativo."""
        state = self.load_state()
        state.active_plan = plan
        self.save_state(state)

    def get_active_plan(self, target_date: Optional[str] = None) -> Optional[DailyPlan]:
        """Recupera o plano ativo para a data especificada."""
        state = self.load_state()
        if state.active_plan:
            if target_date is None or state.active_plan.date == target_date:
                return state.active_plan
        return None
