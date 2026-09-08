"""Agente Especialista em Curadoria e Geração de Listas de Exercícios (ExerciseCurator)."""

from datetime import datetime
from typing import List, Optional
from core.models import ExerciseItem, ExerciseList


class ExerciseCurator:
    """Curador inteligente de questões pedagógicas estruturadas em 3 níveis."""

    LEVEL_CONFIG = {
        1: ("Nível 1 — Básico / Fundamentação", 3),
        2: ("Nível 2 — Intermediário / Consolidação", 4),
        3: ("Nível 3 — Avançado / Aprofundamento", 3),
    }

    def __init__(self):
        pass

    def _resolve_default_source(self, track_id: str, topic_name: str) -> str:
        tid = track_id.lower()
        top = topic_name.lower()
        if "comvest" in tid or "unicamp" in tid:
            return "Banca Comvest / Unicamp (1ª e 2ª Fases)"
        elif "faculdade" in tid or any(k in top for k in ["calculo", "algebra", "algoritmo", "ga_"]):
            return "Livros Universitários Canônicos (Guidorizzi / Stewart / Steinbruch / Cormen)"
        elif "ia" in tid or "machine_learning" in tid:
            return "Fundamentos Matemáticos de ML & Implementações Seminais"
        return "Bancas de Alto Rendimento e Bibliografia Oficial"

    def curate_exercise_list(
        self,
        topic_name: str,
        track_id: str,
        source_scope: Optional[str] = None,
        target_accuracy: float = 0.80
    ) -> ExerciseList:
        """Gera uma lista estruturada com exatamente 3 questões N1, 4 questões N2 e 3 questões N3."""
        scope = source_scope or self._resolve_default_source(track_id, topic_name)
        exercises: List[ExerciseItem] = []

        # Nível 1: 3 Questões (Básico / Fundamentação)
        exercises.extend(self._generate_level_1(topic_name, scope))

        # Nível 2: 4 Questões (Intermediário / Consolidação)
        exercises.extend(self._generate_level_2(topic_name, scope))

        # Nível 3: 3 Questões (Avançado / Aprofundamento)
        exercises.extend(self._generate_level_3(topic_name, scope))

        exercise_list = ExerciseList(
            track_id=track_id,
            topic_name=topic_name,
            source_scope=scope,
            target_accuracy=target_accuracy,
            created_at=datetime.now().isoformat(),
            exercises=exercises
        )
        return exercise_list

    def _generate_level_1(self, topic: str, scope: str) -> List[ExerciseItem]:
        return [
            ExerciseItem(
                id="ex_n1_01",
                level=1,
                level_name=self.LEVEL_CONFIG[1][0],
                statement=f"[Definição Fundamental] Enuncie a definição conceitual central de '{topic}' e identifique as condições de existência ou propriedades axiomáticas indispensáveis.",
                answer_key=f"A definição formal de {topic} requer a verificação direta dos axiomas ou equações de base, garantindo domínio e continuidade conforme o escopo ({scope}).",
                explanation="Questão direta de checagem conceitual para evitar erros preliminares por memorização passiva.",
                source=f"{scope} - Questão Conceitual Direta"
            ),
            ExerciseItem(
                id="ex_n1_02",
                level=1,
                level_name=self.LEVEL_CONFIG[1][0],
                statement=f"[Aplicação Imediata de Fórmula] Dados os parâmetros primários padrão para '{topic}', calcule o resultado direto aplicando a fórmula/algoritmo canônico sem transformações algébricas intermediárias.",
                options=[
                    "A) Resolução escalar direta sem termo residual",
                    "B) Resolução com divergência de sinal",
                    "C) Indeterminação algébrica",
                    "D) Resolução nula"
                ],
                answer_key="A) Resolução escalar direta sem termo residual",
                explanation="Fixação do algoritmo operacional fundamental e verificação de sinais.",
                source=f"{scope} - Exercício de Fixação"
            ),
            ExerciseItem(
                id="ex_n1_03",
                level=1,
                level_name=self.LEVEL_CONFIG[1][0],
                statement=f"[Análise de Gráficos e Representações] Analise o comportamento elementar da representação geométrica ou gráfica associada a '{topic}' e determine o ponto crítico ou intercepto.",
                answer_key="Intercepto obtido igualando a variável independente ou dependente a zero no modelo canônico.",
                explanation="Associação visual imediata entre a fórmula algébrica e o comportamento no plano cartesiano.",
                source=f"{scope} - Leitura Básica"
            )
        ]

    def _generate_level_2(self, topic: str, scope: str) -> List[ExerciseItem]:
        return [
            ExerciseItem(
                id="ex_n2_01",
                level=2,
                level_name=self.LEVEL_CONFIG[2][0],
                statement=f"[Manipulação Algébrica Padrão] Simplifique a expressão algébrica e resolva a equação canônica de '{topic}' sujeita a restrições de contorno.",
                answer_key="Desenvolvimento algébrico completo com isolamento da variável e teste das raízes aparentes.",
                explanation="Desenvolve destreza técnica e eliminação de fatores comuns em tempo de prova.",
                source=f"{scope} - Questão Padrão de 1ª Fase / Prova P1"
            ),
            ExerciseItem(
                id="ex_n2_02",
                level=2,
                level_name=self.LEVEL_CONFIG[2][0],
                statement=f"[Problema Contextualizado de Aplicação] Uma situação física/geométrica modelada por '{topic}' possui taxas de variação constantes ou parâmetros definidos. Encontre o valor ótimo ou tempo decorrido.",
                answer_key="Equacionamento do modelo em função dos dados do enunciado e resolução analítica direta.",
                explanation="Tradução da linguagem natural para a formalização matemática correta.",
                source=f"{scope} - Aplicação Modelo"
            ),
            ExerciseItem(
                id="ex_n2_03",
                level=2,
                level_name=self.LEVEL_CONFIG[2][0],
                statement=f"[Intersecção e Sistemas] Resolva o sistema de equações que envolve '{topic}' e uma restrição linear secundária, encontrando todos os pontos de contato ou soluções reais.",
                answer_key="Resolução por substituição ou eliminação gaussiana gerando soluções reais e análise de multiplicidade.",
                explanation="Treinamento de métodos de resolução de sistemas não lineares frequentes.",
                source=f"{scope} - Exame Intermediário"
            ),
            ExerciseItem(
                id="ex_n2_04",
                level=2,
                level_name=self.LEVEL_CONFIG[2][0],
                statement=f"[Determinação de Parâmetros Incógnitos] Sabendo que uma curva ou modelo de '{topic}' passa por determinados pontos singulares, determine os coeficientes desconhecidos da equação geral.",
                answer_key="Montagem do sistema de coeficientes e obtenção dos valores unívocos.",
                explanation="Exige trabalhar de trás para frente a partir das propriedades dadas.",
                source=f"{scope} - Consolidação Técnica"
            )
        ]

    def _generate_level_3(self, topic: str, scope: str) -> List[ExerciseItem]:
        return [
            ExerciseItem(
                id="ex_n3_01",
                level=3,
                level_name=self.LEVEL_CONFIG[3][0],
                statement=f"[Discursiva Avançada / 2ª Fase] Considere a família de curvas ou operadores regidos por '{topic}'.\n"
                          f"a) Demonstre analiticamente a propriedade de invariância ou conservação sob transformações ortogonais.\n"
                          f"b) Determine o lugar geométrico dos pontos tais que a relação métrica permaneça constante sob parametrização angular.",
                answer_key="Item a: Demonstração formal via coordenadas ou propriedades intrínsecas.\nItem b: Dedução da equação reduzida do lugar geométrico característico.",
                explanation="Padrão exigente de 2ª fase discursiva com rigor de demonstração matemática e justificativa passo a passo.",
                source=f"{scope} - Questão Discursiva de Alta Dificuldade (2ª Fase)"
            ),
            ExerciseItem(
                id="ex_n3_02",
                level=3,
                level_name=self.LEVEL_CONFIG[3][0],
                statement=f"[Otimização e Máximos/Mínimos com Restrições] Determine as dimensões extremas ou valores assintóticos para o sistema associado a '{topic}', justificando a unicidade do ponto de sela ou extremo local sem uso de calculadoras.",
                answer_key="Derivação formal ou desigualdade geométrica (MA-MG / Cauchy-Schwarz) estabelecendo o limite estrito.",
                explanation="Combina conhecimentos transversais de álgebra com cálculo ou geometria pura.",
                source=f"{scope} - Desafio de Aprofundamento"
            ),
            ExerciseItem(
                id="ex_n3_03",
                level=3,
                level_name=self.LEVEL_CONFIG[3][0],
                statement=f"[Problema Integrador Multidisciplinar] Articule os princípios de '{topic}' com um fenômeno físico ou algorítmico correlato (ex.: propagação ondulatória, conservação de energia ou complexidade assintótica). Calcule o coeficiente crítico de estabilidade.",
                answer_key="Equação diferencial ou polinomial resolvida com raízes complexas/reais e análise de estabilidade assintótica.",
                explanation="Desenvolve a capacidade de transferência analítica entre áreas exigida no topo dos vestibulares e na graduação.",
                source=f"{scope} - Questão Integrativa de Alto Nível"
            )
        ]
