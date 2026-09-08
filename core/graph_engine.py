"""Motor de topologia em grafo (DAG), regras de progressão e desbloqueio por maestria."""

from typing import Dict, List, Optional, Set, Tuple

from core.models import StudyTrack, TopicNode, TopicStatus


class GraphEngine:
    """Gerencia a progressão e desbloqueio de habilidades no Grafo Acíclico Dirigido (DAG)."""

    @staticmethod
    def initialize_track_graph(track: StudyTrack) -> None:
        """Inicializa ou recalibra o estado dos nós do grafo respeitando a ordem de pré-requisitos."""
        if not track.nodes:
            return

        # Valida integridade do DAG
        track.validate_dag()

        # Primeiro passo: nós sem pré-requisitos começam em UNLOCKED (se ainda estiverem LOCKED)
        for node in track.nodes.values():
            if not node.prerequisites and node.status == TopicStatus.LOCKED:
                node.status = TopicStatus.UNLOCKED

        # Segundo passo: para nós com pré-requisitos, verifica se já podem ser desbloqueados
        for node in track.nodes.values():
            if node.status == TopicStatus.LOCKED:
                all_met = all(
                    track.nodes[p].status == TopicStatus.MASTERED
                    for p in node.prerequisites
                )
                if all_met:
                    node.status = TopicStatus.UNLOCKED

    @staticmethod
    def update_topic_progress(
        track: StudyTrack,
        topic_id: str,
        correct: int,
        total: int,
        deliverable_done: bool = True
    ) -> Tuple[bool, List[str]]:
        """Registra resultado prático em um nó e desbloqueia nós dependentes em caso de maestria.
        
        Retorna:
            (was_mastered, newly_unlocked_node_ids)
        """
        if topic_id not in track.nodes:
            return False, []

        node = track.nodes[topic_id]
        became_mastered = node.update_progress(correct, total, deliverable_done)
        newly_unlocked: List[str] = []

        if became_mastered:
            # Percorre nós filhos que dependem deste nó
            for candidate_id, candidate in track.nodes.items():
                if candidate.status == TopicStatus.LOCKED and topic_id in candidate.prerequisites:
                    # Checa se TODOS os pré-requisitos do candidato agora estão dominados
                    all_prereqs_mastered = all(
                        track.nodes[p].status == TopicStatus.MASTERED
                        for p in candidate.prerequisites
                    )
                    if all_prereqs_mastered:
                        candidate.status = TopicStatus.UNLOCKED
                        newly_unlocked.append(candidate_id)

        return became_mastered, newly_unlocked

    @staticmethod
    def get_available_topics(
        track: StudyTrack,
        subject: Optional[str] = None
    ) -> List[TopicNode]:
        """Retorna todos os nós liberados ou em andamento prontos para estudo."""
        if not track.nodes:
            return []

        available = [
            n for n in track.nodes.values()
            if n.status in (TopicStatus.UNLOCKED, TopicStatus.IN_PROGRESS)
        ]

        if subject:
            sub_lower = subject.lower().strip()
            available = [n for n in available if n.subject.lower() == sub_lower]

        return available

    @staticmethod
    def get_dependent_children(track: StudyTrack, node_id: str) -> List[TopicNode]:
        """Retorna os nós dependentes diretos que têm node_id como pré-requisito."""
        return [
            node for node in track.nodes.values()
            if node_id in node.prerequisites
        ]

    @staticmethod
    def is_track_complete(track: StudyTrack) -> bool:
        """Verifica se o objetivo final da trilha (target_node ou todos os nós) foi atingido."""
        if not track.nodes:
            return False

        if track.target_node and track.target_node in track.nodes:
            return track.nodes[track.target_node].status == TopicStatus.MASTERED

        return all(n.status == TopicStatus.MASTERED for n in track.nodes.values())
