"""Agente especialista em design curricular autônomo, geração orientada por destino e retroalimentação."""

import re
from typing import Dict, List, Optional, Tuple

from core.graph_engine import GraphEngine
from core.models import StudyTrack, SubjectConfig, TopicNode, TopicStatus
from integrations.notebooklm import NotebookLMClient


class CurriculumAgent:
    """Projeta cadeias curriculares em DAG ligando nó de partida (origem) ao destino final."""

    def __init__(self, notebook_client: Optional[NotebookLMClient] = None):
        self.notebook_client = notebook_client or NotebookLMClient()

    def generate_guided_curriculum(
        self,
        track_id: str,
        name: str,
        origin: str,
        destination: str,
        prompt: Optional[str] = None,
        notebook_id: Optional[str] = None,
        target_date: Optional[str] = None
    ) -> StudyTrack:
        """Gera uma trilha com cadeia de nós intermediários conectando origem ao destino."""
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", track_id.lower().strip()).strip("_")
        track = StudyTrack(
            id=slug,
            name=name,
            description=f"Cadeia curricular guiada de '{origin}' até '{destination}'. {prompt or ''}".strip(),
            target_date=target_date,
            notebook_id=notebook_id or f"nlm_{slug}",
            origin_node=None,
            target_node=None,
            subjects={},
            nodes={},
            is_active=True
        )

        # Mapeia disciplina padrão
        subject_id = "computacao_teorica" if any(w in (origin + destination).lower() for w in ["computa", "cripto", "algoritmo", "ia"]) else "geral"
        subject_name = "Ciência da Computação & Fundamentos" if subject_id == "computacao_teorica" else "Disciplina Central"
        track.subjects[subject_id] = SubjectConfig(
            id=subject_id,
            name=subject_name,
            subject_type="computacao",
            weight=3.0,
            weekly_questions_goal=15,
            requires_tangible_deliverable=True
        )

        # Decompõe e gera os nós intermediários da cadeia
        chain_milestones = self._build_intermediate_milestones(origin, destination, prompt)
        previous_node_id: Optional[str] = None

        for idx, (title, deliverable, subject_key) in enumerate(chain_milestones):
            node_slug = f"n{idx+1:02d}_{re.sub(r'[^a-zA-Z0-9_]+', '_', title.lower())[:24].strip('_')}"
            prereqs = [previous_node_id] if previous_node_id else []

            node = TopicNode(
                id=node_slug,
                name=title,
                subject=subject_name,
                prerequisites=prereqs,
                mastery_threshold=0.80,
                status=TopicStatus.LOCKED,
                deliverable_template=deliverable,
                notebook_ref=f"NotebookLM: {track.name} > Tópico: {title}"
            )
            track.nodes[node_slug] = node

            if idx == 0:
                track.origin_node = node_slug
            if idx == len(chain_milestones) - 1:
                track.target_node = node_slug

            previous_node_id = node_slug

        # Inicializa status de desbloqueio
        GraphEngine.initialize_track_graph(track)
        return track

    def _build_intermediate_milestones(
        self,
        origin: str,
        destination: str,
        prompt: Optional[str] = None
    ) -> List[Tuple[str, str, str]]:
        """Calcula os passos intermediários necessários entre origem e destino."""
        orig_lower = origin.lower()
        dest_lower = destination.lower()

        # Roteamento especializado para Computação -> Criptografia
        if ("computa" in orig_lower or "automato" in orig_lower or "algoritmo" in orig_lower) and ("cripto" in dest_lower):
            return [
                (
                    f"{origin}: Modelos Formais e Complexidade",
                    "Demonstrar reduções polinomiais e limites assintóticos de complexidade para problemas em P e NP",
                    "computacao"
                ),
                (
                    "Aritmética Modular e Teoria dos Números",
                    "Implementar algoritmo estendido de Euclides, exponenciação modular rápida e teste de primalidade Miller-Rabin",
                    "computacao"
                ),
                (
                    "Fundamentos de Criptografia Simétrica",
                    "Implementar cifra de bloco simplificada (SPN) e analisar modos de operação (CBC e GCM) contra ataques de repetição",
                    "computacao"
                ),
                (
                    "Criptografia Assimétrica e Troca de Chaves",
                    "Implementar protocolo Diffie-Hellman e sistema RSA com geração de chaves coprimas em Python puro",
                    "computacao"
                ),
                (
                    f"{destination}: Aplicações Avançadas e Provas de Conhecimento Zero",
                    "Implementar protótipo funcional de assinatura digital ou esquema ZKP com verificação formal",
                    "computacao"
                ),
            ]

        # Roteamento especializado para Redes Neurais -> LLMs/RAG
        elif ("neural" in orig_lower or "deep learning" in orig_lower) and ("llm" in dest_lower or "rag" in dest_lower):
            return [
                (
                    f"{origin}: Perceptron e Backpropagation",
                    "Implementar MLP com forward e backward pass manuais em NumPy e testar convergência",
                    "computacao"
                ),
                (
                    "Arquitetura Transformer e Mecanismo de Atenção",
                    "Implementar Scaled Dot-Product Attention e Multi-Head Attention em PyTorch puro",
                    "computacao"
                ),
                (
                    "Tokenização e Pré-treinamento Autorregressivo",
                    "Treinar mini-GPT com Byte-Pair Encoding (BPE) em corpus pequeno",
                    "computacao"
                ),
                (
                    f"{destination}: Indexação Vetorial e Recuperação Aumentada",
                    "Construir pipeline RAG com busca híbrida densa/esparsa, re-ranking e avaliação de grounding",
                    "computacao"
                ),
            ]

        # Caso geral guiado por prompt ou decomposição linear
        else:
            custom_items = []
            if prompt:
                # Divide tópicos separados por vírgula ou ponto e vírgula
                parts = [p.strip() for p in re.split(r"[,;\n]+", prompt) if len(p.strip()) > 3]
                if parts:
                    for p in parts:
                        custom_items.append((
                            p,
                            f"Resolver lista prática e implementar caso de estudo concreto de {p}",
                            "geral"
                        ))

            if not custom_items:
                custom_items = [
                    (
                        f"Fundamentos de {origin}",
                        f"Mapear 10 conceitos estruturais e resolver exercícios fundamentais de {origin}",
                        "geral"
                    ),
                    (
                        f"Conexões e Aplicações Intermediárias de {origin}",
                        f"Construir projeto ou resolução analítica conectando {origin} aos requisitos de {destination}",
                        "geral"
                    ),
                    (
                        f"Domínio Avançado de {destination}",
                        f"Concluir projeto integrador e testes rigorosos demonstrando maestria em {destination}",
                        "geral"
                    ),
                ]

            return custom_items

    def check_and_expand_curriculum(self, track: StudyTrack) -> Optional[TopicNode]:
        """Retroalimentação: se a maioria dos nós foi dominada mas o target não, expande nós de aprofundamento."""
        if not track.nodes:
            return None

        mastered_count = sum(1 for n in track.nodes.values() if n.status == TopicStatus.MASTERED)
        total_count = len(track.nodes)

        # Se mais de 70% dos nós estão dominados e o nó alvo não está completo
        if track.target_node and track.nodes.get(track.target_node):
            target = track.nodes[track.target_node]
            if target.status != TopicStatus.MASTERED and mastered_count >= total_count - 1:
                # Cria nó de consolidação antes do target se não existir
                deepening_id = f"n_deep_{track.target_node}"
                if deepening_id not in track.nodes:
                    node = TopicNode(
                        id=deepening_id,
                        name=f"Laboratório de Consolidação e Casos Extremos ({target.name})",
                        subject=target.subject,
                        prerequisites=[p for p in target.prerequisites if p in track.nodes],
                        mastery_threshold=0.85,
                        status=TopicStatus.UNLOCKED,
                        deliverable_template=f"Desenvolver bateria de 10 testes de estresse e casos de borda em {target.name}",
                        notebook_ref=f"NotebookLM: {track.name} > Tópico de Aprofundamento"
                    )
                    track.nodes[deepening_id] = node
                    # Adiciona aos pré-requisitos do target
                    if deepening_id not in target.prerequisites:
                        target.prerequisites.append(deepening_id)
                    GraphEngine.initialize_track_graph(track)
                    return node

        return None
