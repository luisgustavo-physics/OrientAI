"""Configurações das matérias, pesos da Unicamp e templates de entregáveis tangíveis."""

from enum import Enum
from typing import Dict, List
from core.models import SubjectConfig


class SubjectType(str, Enum):
    EXATAS = "exatas"
    HUMANAS = "humanas"
    BIOLOGICAS = "biologicas"
    LINGUAGENS = "linguagens"


class Subject(str, Enum):
    MATEMATICA = "matematica"
    FISICA = "fisica"
    QUIMICA = "quimica"
    BIOLOGIA = "biologia"
    HISTORIA = "historia"
    GEOGRAFIA = "geografia"
    PORTUGUES = "portugues"
    INGLES = "ingles"
    COMPUTACAO = "computacao"


# Configuração padrão pré-populada com foco na Unicamp (Ênfase em Ciências Exatas/Tecnologia)
DEFAULT_SUBJECTS: Dict[str, SubjectConfig] = {
    Subject.MATEMATICA.value: SubjectConfig(
        id=Subject.MATEMATICA.value,
        name="Matemática",
        subject_type=SubjectType.EXATAS.value,
        weight=3.0,
        weekly_questions_goal=40,
        anki_deck="Unicamp::Matemática",
        requires_tangible_deliverable=True,
        deliverable_templates=[
            "Resolver 6 questões discursivas da 2ª Fase Unicamp com resolução comentada no caderno/notion",
            "Deduzir e aplicar 3 propriedades analíticas de Geometria/Álgebra em 5 problemas-desafio",
            "Mapear e resolver lista de 8 exercícios de tópicos recorrentes (Funções, Combinatória, Polinômios)"
        ],
    ),
    Subject.FISICA.value: SubjectConfig(
        id=Subject.FISICA.value,
        name="Física",
        subject_type=SubjectType.EXATAS.value,
        weight=2.5,
        weekly_questions_goal=35,
        anki_deck="Unicamp::Física",
        requires_tangible_deliverable=True,
        deliverable_templates=[
            "Resolver 5 questões de provas anteriores Unicamp (Mecânica/Termodinâmica/Eletromagnetismo)",
            "Esquematizar diagrama de forças e equacionar 4 problemas complexos de dinâmica/óptica",
            "Resolução de lista comentada de 6 exercícios focados em interpretação gráfica e física aplicada"
        ],
    ),
    Subject.QUIMICA.value: SubjectConfig(
        id=Subject.QUIMICA.value,
        name="Química",
        subject_type=SubjectType.EXATAS.value,
        weight=2.0,
        weekly_questions_goal=30,
        anki_deck="Unicamp::Química",
        requires_tangible_deliverable=True,
        deliverable_templates=[
            "Balancear reações e resolver 5 exercícios de estequiometria/soluções com passos de cálculo",
            "Resolver 5 questões discursivas de Físico-Química ou Química Orgânica (mecanismos e isomeria)",
            "Análise quantitativa de 4 questões envolvendo equilíbrio químico e cinemática de reações"
        ],
    ),
    Subject.BIOLOGIA.value: SubjectConfig(
        id=Subject.BIOLOGIA.value,
        name="Biologia",
        subject_type=SubjectType.BIOLOGICAS.value,
        weight=1.5,
        weekly_questions_goal=25,
        anki_deck="Unicamp::Biologia",
        requires_tangible_deliverable=False,
        deliverable_templates=[
            "Criar 10 flashcards no Anki com conceitos-chave e resolver 8 questões de Ecologia/Genética",
            "Mapeamento conceitual esquemático de Fisiologia Humana + 6 questões 1ª Fase Unicamp"
        ],
    ),
    Subject.HISTORIA.value: SubjectConfig(
        id=Subject.HISTORIA.value,
        name="História",
        subject_type=SubjectType.HUMANAS.value,
        weight=1.5,
        weekly_questions_goal=20,
        anki_deck="Unicamp::História",
        requires_tangible_deliverable=False,
        deliverable_templates=[
            "Redigir 3 respostas modelo para questões discursivas de História do Brasil com fontes primárias",
            "Criar linha do tempo comparativa + revisão de 15 cards do deck de História Geral"
        ],
    ),
    Subject.GEOGRAFIA.value: SubjectConfig(
        id=Subject.GEOGRAFIA.value,
        name="Geografia",
        subject_type=SubjectType.HUMANAS.value,
        weight=1.5,
        weekly_questions_goal=20,
        anki_deck="Unicamp::Geografia",
        requires_tangible_deliverable=False,
        deliverable_templates=[
            "Analisar 4 gráficos/mapas de demografia/climatologia e responder 6 questões da Unicamp",
            "Escrever síntese sobre geopolítica contemporânea aplicada a 4 exercícios discursivos"
        ],
    ),
    Subject.PORTUGUES.value: SubjectConfig(
        id=Subject.PORTUGUES.value,
        name="Língua Portuguesa e Literatura",
        subject_type=SubjectType.LINGUAGENS.value,
        weight=2.0,
        weekly_questions_goal=25,
        anki_deck="Unicamp::Literatura",
        requires_tangible_deliverable=False,
        deliverable_templates=[
            "Fichamento crítico de uma obra obrigatória da Unicamp + resolução de 4 questões discursivas",
            "Elaboração de rascunho de proposta de redação Unicamp no gênero textual solicitado"
        ],
    ),
    Subject.INGLES.value: SubjectConfig(
        id=Subject.INGLES.value,
        name="Inglês",
        subject_type=SubjectType.LINGUAGENS.value,
        weight=1.0,
        weekly_questions_goal=15,
        anki_deck="Unicamp::Inglês",
        requires_tangible_deliverable=False,
        deliverable_templates=[
            "Leitura crítica de 2 artigos científicos/jornalísticos em inglês e resolução de 6 questões",
            "Extração de vocabulário e expressões idiomáticas para 10 novos cards no Anki"
        ],
    ),
    Subject.COMPUTACAO.value: SubjectConfig(
        id=Subject.COMPUTACAO.value,
        name="Computação & Raciocínio Lógico",
        subject_type=SubjectType.EXATAS.value,
        weight=2.5,
        weekly_questions_goal=15,
        anki_deck="Academia::Algoritmos",
        requires_tangible_deliverable=True,
        deliverable_templates=[
            "Implementar em Python 1 estrutura de dados ou algoritmo de ordenação/busca com testes unitários",
            "Resolver 2 problemas estilo Beecrowd/LeetCode com análise de complexidade O(n)",
            "Criar script de automação prático ou resolver problemas de lógica computacional com código"
        ],
    ),
}
