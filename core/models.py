"""Modelos de dados para o agendador, trilhas de estudo em grafo (DAG), logs e métricas."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field, model_validator


class ActivityType(str, Enum):
    QUESTOES = "questoes"
    DISCURSIVA = "discursiva"
    IMPLEMENTACAO = "implementacao"
    ANKI_REVISAO = "anki_revisao"
    CRIACAO_CARDS = "criacao_cards"
    PROJETO = "projeto"
    LEITURA_ATIVA = "leitura_ativa"


class TopicStatus(str, Enum):
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"
    IN_PROGRESS = "IN_PROGRESS"
    MASTERED = "MASTERED"


class SubjectConfig(BaseModel):
    """Configuração de uma disciplina dentro de uma trilha de estudo."""
    id: str
    name: str
    subject_type: str = "geral"
    weight: float = Field(default=1.0, description="Peso da matéria na trilha")
    weekly_questions_goal: int = Field(default=30, description="Meta semanal de questões ou entregáveis")
    anki_deck: Optional[str] = Field(default=None, description="Deck associado no Anki")
    requires_tangible_deliverable: bool = Field(
        default=False,
        description="Obriga entrega de código, deduções ou resolução de exercícios práticos"
    )
    deliverable_templates: List[str] = Field(
        default_factory=list,
        description="Opções de entregáveis tangíveis para blocos de estudo"
    )


class TopicNode(BaseModel):
    """Nó atômico de conteúdo dentro do Grafo Acíclico Dirigido (DAG) de uma trilha."""
    id: str
    name: str
    subject: str
    prerequisites: List[str] = Field(default_factory=list, description="IDs dos nós pré-requisitos necessários")
    mastery_threshold: float = Field(default=0.80, description="Taxa mínima de acerto (ex: 80%) para maestria")
    current_accuracy: float = 0.0
    total_questions: int = 0
    correct_answers: int = 0
    status: TopicStatus = TopicStatus.LOCKED
    deliverable_template: Optional[str] = None
    notebook_ref: Optional[str] = Field(default=None, description="Referência ou citação do material no NotebookLM")

    def update_progress(self, correct: int, total: int, deliverable_done: bool = True) -> bool:
        """Atualiza estatísticas do nó e avalia maestria. Retorna True se atingiu maestria agora."""
        self.total_questions += total
        self.correct_answers += correct
        if self.total_questions > 0:
            self.current_accuracy = round(self.correct_answers / self.total_questions, 4)

        if self.current_accuracy >= self.mastery_threshold and deliverable_done:
            self.status = TopicStatus.MASTERED
            return True
        else:
            if self.status == TopicStatus.LOCKED or self.status == TopicStatus.UNLOCKED:
                self.status = TopicStatus.IN_PROGRESS
            return False


class StudyTrack(BaseModel):
    """Representa uma trilha de estudo estruturada com grafo DAG e integração com NotebookLM."""
    id: str
    name: str
    description: str
    target_date: Optional[str] = Field(default=None, description="Data alvo no formato YYYY-MM-DD")
    notebook_id: Optional[str] = Field(default=None, description="ID do NotebookLM ancorado a esta trilha")
    notebook_sources: List[str] = Field(default_factory=list, description="Fontes e referências indexadas no NotebookLM")
    origin_node: Optional[str] = Field(default=None, description="Nó de partida do grafo")
    target_node: Optional[str] = Field(default=None, description="Nó terminal/objetivo final do grafo")
    subjects: Dict[str, SubjectConfig] = Field(default_factory=dict)
    nodes: Dict[str, TopicNode] = Field(default_factory=dict, description="Grafo de tópicos e habilidades (DAG)")
    is_active: bool = True

    def get_subject(self, subject_id: str) -> Optional[SubjectConfig]:
        """Recupera a configuração da matéria por ID ou nome."""
        if subject_id in self.subjects:
            return self.subjects[subject_id]
        for s in self.subjects.values():
            if s.name.lower() == subject_id.lower():
                return s
        return None

    def validate_dag(self) -> bool:
        """Valida que o grafo de tópicos é um Grafo Acíclico Dirigido (DAG) válido sem ciclos."""
        if not self.nodes:
            return True

        # 1. Verifica se todos os pré-requisitos apontam para nós existentes
        for node_id, node in self.nodes.items():
            for prereq in node.prerequisites:
                if prereq not in self.nodes:
                    raise ValueError(f"Pré-requisito inválido: nó '{node_id}' aponta para pré-requisito inexistente '{prereq}'.")

        # 2. Detecção de ciclos via DFS de 3 cores (0=Branco/Não visitado, 1=Cinza/Em visita, 2=Preto/Concluído)
        visited: Dict[str, int] = {node_id: 0 for node_id in self.nodes}

        def dfs(curr_id: str, path: List[str]) -> None:
            visited[curr_id] = 1
            node = self.nodes[curr_id]
            for prereq in node.prerequisites:
                if visited[prereq] == 1:
                    cycle_str = " -> ".join(path + [curr_id, prereq])
                    raise ValueError(f"Ciclo de dependência detectado no grafo da trilha '{self.id}': {cycle_str}")
                if visited[prereq] == 0:
                    dfs(prereq, path + [curr_id])
            visited[curr_id] = 2

        for node_id in self.nodes:
            if visited[node_id] == 0:
                dfs(node_id, [])

        return True


class StudyBlock(BaseModel):
    """Representa um bloco de estudo de alta intensidade e propósito único."""
    id: str
    track_id: str
    subject_id: str
    subject_name: str
    topic_id: Optional[str] = None
    activity_type: ActivityType
    start_time: str   # "HH:MM"
    end_time: str     # "HH:MM"
    duration_minutes: int
    deliverable: str  # Entregável tangível obrigatório
    requires_tangible: bool = False
    completed: bool = False
    actual_minutes: Optional[int] = None
    notes: Optional[str] = None


class DailyPlan(BaseModel):
    """Plano diário de estudo gerado pelo agendador."""
    date: str  # "YYYY-MM-DD"
    blocks: List[StudyBlock] = Field(default_factory=list)
    total_planned_minutes: int = 0
    commitments_accounted: List[str] = Field(default_factory=list)
    anki_pending_cards: int = 0
    focus_summary: str = ""
    active_tracks: List[str] = Field(default_factory=list)


class StudyLog(BaseModel):
    """Registro de sessão de estudo executada com métricas concretas."""
    id: str
    track_id: str = "unicamp_cc"
    topic_id: Optional[str] = None
    date: str  # "YYYY-MM-DD"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    subject: str
    correct_answers: int = Field(ge=0)
    total_questions: int = Field(gt=0)
    accuracy_rate: float = Field(ge=0.0, le=1.0)
    minutes_spent: int = Field(gt=0)
    deliverable_completed: bool = True
    deliverable_description: Optional[str] = None
    notes: Optional[str] = None


class SubjectProgress(BaseModel):
    """Histórico acumulado de desempenho em cada matéria."""
    subject: str
    track_id: Optional[str] = None
    total_questions_solved: int = 0
    total_questions_correct: int = 0
    accuracy_rate: float = 0.0
    total_minutes_studied: int = 0
    last_studied_date: Optional[str] = None
    anki_cards_reviewed: int = 0
    sessions_count: int = 0

    def update_with_log(self, log: StudyLog) -> None:
        self.total_questions_solved += log.total_questions
        self.total_questions_correct += log.correct_answers
        if self.total_questions_solved > 0:
            self.accuracy_rate = round(self.total_questions_correct / self.total_questions_solved, 4)
        self.total_minutes_studied += log.minutes_spent
        self.last_studied_date = log.date
        self.sessions_count += 1


class AppState(BaseModel):
    """Estado persistente do agente de estudos."""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    subjects: Dict[str, SubjectProgress] = Field(default_factory=dict)
    logs: List[StudyLog] = Field(default_factory=list)
    active_plan: Optional[DailyPlan] = None


class ExerciseItem(BaseModel):
    """Representa um item/questão de uma lista de exercícios."""
    id: str
    level: int = Field(ge=1, le=3, description="Nível da questão (1, 2 ou 3)")
    level_name: str = Field(description="Nome do nível (ex: Nível 1 - Básico/Fundamentação)")
    statement: str = Field(description="Enunciado completo da questão")
    options: Optional[List[str]] = Field(default=None, description="Alternativas caso seja de múltipla escolha")
    answer_key: str = Field(description="Gabarito oficial ou resolução esperada")
    explanation: Optional[str] = Field(default=None, description="Explicação conceitual / passo a passo")
    source: Optional[str] = Field(default=None, description="Fonte / Prova de origem")


class ExerciseList(BaseModel):
    """Lista de exercícios com divisão rígida em 3 níveis pedagógicos."""
    track_id: str
    topic_name: str
    source_scope: str
    target_accuracy: float = Field(default=0.80, description="Meta de acertos (ex: 80%)")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    exercises: List[ExerciseItem] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_levels_distribution(self) -> 'ExerciseList':
        if not self.exercises:
            return self
        lvl1 = [e for e in self.exercises if e.level == 1]
        lvl2 = [e for e in self.exercises if e.level == 2]
        lvl3 = [e for e in self.exercises if e.level == 3]
        if len(lvl1) != 3 or len(lvl2) != 4 or len(lvl3) != 3:
            raise ValueError(
                f"ExerciseList deve conter exatamente 3 questões de Nível 1, 4 de Nível 2 e 3 de Nível 3. "
                f"Encontrado: N1={len(lvl1)}, N2={len(lvl2)}, N3={len(lvl3)}."
            )
        return self

