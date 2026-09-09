"""Agente Especialista em Curadoria e Geração de Listas de Exercícios (ExerciseCurator).

Utiliza GeminiClient com Long Context e Grounding via KnowledgeStore para gerar
listas estruturadas de alto rendimento divididas em 3 níveis (3 N1, 4 N2, 3 N3),
salvando os entregáveis em Markdown e HTML limpo em data/worksheets/.
"""

import html
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from config.settings import Settings, get_settings
from core.knowledge_store import KnowledgeStore
from core.models import ExerciseItem, ExerciseList
from integrations.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class ExerciseCurator:
    """Curador inteligente de questões pedagógicas estruturadas em 3 níveis."""

    LEVEL_CONFIG = {
        1: ("Nível 1 — Básico / Fundamentação", 3),
        2: ("Nível 2 — Intermediário / Consolidação", 4),
        3: ("Nível 3 — Avançado / Aprofundamento", 3),
    }

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        knowledge_store: Optional[KnowledgeStore] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.gemini_client = gemini_client
        self.knowledge_store = knowledge_store or KnowledgeStore(settings=self.settings)

    def _slugify(self, text: str) -> str:
        text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        return re.sub(r"[\s_-]+", "_", text).strip("_")

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
        target_accuracy: float = 0.80,
    ) -> ExerciseList:
        """Gera uma lista estruturada com exatamente 3 questões N1, 4 questões N2 e 3 questões N3.

        Prioriza geração via GeminiClient com ancoragem no KnowledgeStore; se indisponível ou offline,
        aciona o fallback heurístico canônico.
        """
        scope = source_scope or self._resolve_default_source(track_id, topic_name)

        # 1. Tenta geração ancorada via GeminiClient se configurado
        if self.gemini_client and self.gemini_client.is_configured():
            try:
                return self._generate_with_gemini(
                    topic_name=topic_name,
                    track_id=track_id,
                    scope=scope,
                    target_accuracy=target_accuracy
                )
            except Exception as e:
                logger.warning(f"Falha na geração via Gemini ({e}). Acionando fallback heurístico.")

        # 2. Fallback determinístico offline
        return self._generate_fallback_list(topic_name, track_id, scope, target_accuracy)

    def _generate_with_gemini(
        self,
        topic_name: str,
        track_id: str,
        scope: str,
        target_accuracy: float
    ) -> ExerciseList:
        """Executa a geração estruturada via Gemini com injeção de contexto das fontes da trilha."""
        system_instruction = self.knowledge_store.get_grounded_system_instruction(
            track_id=track_id,
            base_instruction=(
                "Você é um curador pedagógico e examinador de alto nível técnico do OrientAI.\n"
                "Sua missão é curar e elaborar uma lista de 10 exercícios tangíveis e rigorosos.\n"
                "A lista deve atender estritamente à distribuição de 3 níveis de maestria:\n"
                "- Nível 1 (Básico / Fundamentação): exatamente 3 questões.\n"
                "- Nível 2 (Intermediário / Consolidação): exatamente 4 questões.\n"
                "- Nível 3 (Avançado / Aprofundamento): exatamente 3 questões.\n"
                "Forneça gabarito definitivo e critérios de correção detalhados para cada questão."
            )
        )

        prompt = (
            f"Elabore uma lista completa de 10 exercícios para o seguinte conteúdo:\n\n"
            f"- **Trilha:** {track_id}\n"
            f"- **Tópico de Estudo:** {topic_name}\n"
            f"- **Escopo / Bibliografia:** {scope}\n"
            f"- **Meta de Acerto:** {int(target_accuracy * 100)}%\n\n"
            f"Requisitos Estruturais Obrigatórios:\n"
            f"1. A lista DEVE conter exatamente 10 exercícios:\n"
            f"   - 3 itens com level=1, level_name='Nível 1 — Básico / Fundamentação' (IDs: ex_n1_01, ex_n1_02, ex_n1_03)\n"
            f"   - 4 itens com level=2, level_name='Nível 2 — Intermediário / Consolidação' (IDs: ex_n2_01, ex_n2_02, ex_n2_03, ex_n2_04)\n"
            f"   - 3 itens com level=3, level_name='Nível 3 — Avançado / Aprofundamento' (IDs: ex_n3_01, ex_n3_02, ex_n3_03)\n"
            f"2. Em cada questão, forneça:\n"
            f"   - statement: enunciado completo, claro e matematicamente correto.\n"
            f"   - options: lista de opções A, B, C, D (se múltipla escolha) ou null se discursiva.\n"
            f"   - answer_key: resposta final objetiva ou resultado exato.\n"
            f"   - explanation: dedução passo a passo e critérios rigorosos de pontuação da banca.\n"
            f"   - source: indicação da prova de referência ou livro canônico.\n"
            f"3. Respeite as fontes indexadas da trilha para garantir zero alucinação conceitual."
        )

        # pyrefly: ignore [missing-attribute]
        result = self.gemini_client.generate_structured(
            prompt=prompt,
            response_schema=ExerciseList,
            system_instruction=system_instruction
        )
        return result

    def _generate_fallback_list(
        self,
        topic_name: str,
        track_id: str,
        scope: str,
        target_accuracy: float
    ) -> ExerciseList:
        """Gera lista heurística determinística garantindo o schema ExerciseList."""
        exercises: List[ExerciseItem] = []
        exercises.extend(self._generate_level_1(topic_name, scope))
        exercises.extend(self._generate_level_2(topic_name, scope))
        exercises.extend(self._generate_level_3(topic_name, scope))

        return ExerciseList(
            track_id=track_id,
            topic_name=topic_name,
            source_scope=scope,
            target_accuracy=target_accuracy,
            created_at=datetime.now().isoformat(),
            exercises=exercises
        )

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

    def build_markdown_worksheet(self, exercise_list: ExerciseList) -> str:
        """Gera o texto completo da lista em Markdown estruturado."""
        md_lines = [
            f"# 🎯 OrientAI — Lista de Exercícios de Alta Performance",
            f"",
            f"> **Trilha:** `{exercise_list.track_id}` | **Tópico:** **{exercise_list.topic_name}** | **Meta de Acertos:** `{int(exercise_list.target_accuracy * 100)}%`",
            f"> **Escopo / Bibliografia:** *{exercise_list.source_scope}* | **Gerado em:** `{exercise_list.created_at[:16].replace('T', ' ')}`",
            f"",
            f"---",
            f"",
            f"### 📋 Instruções de Execução (Regra Anti-Passividade)",
            f"1. **Tempo de Resolução Focada:** Dedique blocos de 50 minutos sem interrupções nem consultas prévias ao gabarito.",
            f"2. **Obrigatoriedade de Registro:** Registre toda a demonstração ou rascunho algébrico no quadro de cada questão.",
            f"3. **Maestria do Nó no Grafo:** Para consolidar e desbloquear os nós sucessores no DAG, atinja no mínimo **{int(exercise_list.target_accuracy * 100)}% de acertos**.",
            f"",
            f"---",
            f""
        ]

        for lvl in [1, 2, 3]:
            lvl_items = [e for e in exercise_list.exercises if e.level == lvl]
            if not lvl_items:
                continue
            badge_icon = "🟢" if lvl == 1 else ("🟡" if lvl == 2 else "🔴")
            md_lines.extend([
                f"## {badge_icon} {lvl_items[0].level_name}",
                f""
            ])

            for ex in lvl_items:
                md_lines.extend([
                    f"#### 📝 Questão `{ex.id.upper()}` — *{ex.source or 'Fonte Oficial'}*",
                    f"",
                    f"{ex.statement}",
                    f""
                ])
                if ex.options:
                    for opt in ex.options:
                        md_lines.append(f"- {opt}")
                    md_lines.append("")

                md_lines.extend([
                    f"```text",
                    f"┌─ [RASCUNHO / DEMONSTRAÇÃO DISCURSIVA] ────────────────────────────────────────┐",
                    f"│                                                                               │",
                    f"│                                                                               │",
                    f"│ [ ] Resposta Final do Estudante: ____________________________________________ │",
                    f"└───────────────────────────────────────────────────────────────────────────────┘",
                    f"```",
                    f""
                ])

        md_lines.extend([
            f"---",
            f"",
            f"## 🔑 Gabarito Oficial e Critérios de Correção",
            f"",
            f"| Questão | Nível | Gabarito Oficial | Critério / Explicação |",
            f"| :--- | :--- | :--- | :--- |"
        ])

        for ex in exercise_list.exercises:
            gabarito_limpo = ex.answer_key.replace("\n", " ").replace("|", "/")
            expl_limpo = (ex.explanation or "").replace("\n", " ").replace("|", "/")
            md_lines.append(f"| `{ex.id.upper()}` | N{ex.level} | **{gabarito_limpo}** | {expl_limpo} |")

        md_lines.append("")
        return "\n".join(md_lines)

    def build_html_worksheet(self, exercise_list: ExerciseList) -> str:
        """Gera versão HTML limpa, moderna e responsiva pronta para impressão ou cópia para Google Docs/Obsidian."""
        created_str = exercise_list.created_at[:16].replace("T", " ")
        safe_title = html.escape(f"OrientAI — Lista de Exercícios: {exercise_list.topic_name}")
        safe_topic = html.escape(exercise_list.topic_name)
        safe_track = html.escape(exercise_list.track_id.upper())
        safe_scope = html.escape(exercise_list.source_scope)

        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='pt-BR'>",
            "<head>",
            "  <meta charset='UTF-8'>",
            "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            f"  <title>{safe_title}</title>",
            "  <style>",
            "    :root {",
            "      --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;",
            "      --text-main: #1f2937;",
            "      --text-muted: #4b5563;",
            "      --bg-page: #f9fafb;",
            "      --bg-card: #ffffff;",
            "      --border-color: #e5e7eb;",
            "      --primary: #2563eb;",
            "      --level1: #16a34a;",
            "      --level2: #d97706;",
            "      --level3: #dc2626;",
            "    }",
            "    @media print {",
            "      body { background: #fff !important; font-size: 11pt; }",
            "      .no-print { display: none; }",
            "      .page-break { page-break-before: always; }",
            "      .question-box { page-break-inside: avoid; border: 1px solid #ccc !important; }",
            "    }",
            "    body {",
            "      font-family: var(--font-family);",
            "      background-color: var(--bg-page);",
            "      color: var(--text-main);",
            "      margin: 0;",
            "      padding: 24px;",
            "      line-height: 1.6;",
            "    }",
            "    .container {",
            "      max-width: 860px;",
            "      margin: 0 auto;",
            "      background: var(--bg-card);",
            "      padding: 36px;",
            "      border-radius: 12px;",
            "      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);",
            "      border: 1px solid var(--border-color);",
            "    }",
            "    .header {",
            "      border-bottom: 2px solid var(--border-color);",
            "      padding-bottom: 18px;",
            "      margin-bottom: 24px;",
            "    }",
            "    h1 { margin: 0 0 8px 0; font-size: 24px; color: #111827; }",
            "    .meta-bar {",
            "      display: flex;",
            "      flex-wrap: wrap;",
            "      gap: 12px;",
            "      font-size: 14px;",
            "      color: var(--text-muted);",
            "      margin-top: 10px;",
            "    }",
            "    .badge {",
            "      display: inline-block;",
            "      padding: 3px 10px;",
            "      border-radius: 9999px;",
            "      font-weight: 600;",
            "      font-size: 12px;",
            "    }",
            "    .badge-track { background: #eff6ff; color: #1d4ed8; }",
            "    .badge-target { background: #fdf4ff; color: #a21caf; }",
            "    .section-title {",
            "      display: flex;",
            "      align-items: center;",
            "      gap: 8px;",
            "      font-size: 18px;",
            "      font-weight: 700;",
            "      margin-top: 32px;",
            "      margin-bottom: 16px;",
            "      padding-bottom: 6px;",
            "      border-bottom: 1px solid var(--border-color);",
            "    }",
            "    .question-card {",
            "      border: 1px solid var(--border-color);",
            "      border-radius: 8px;",
            "      padding: 18px;",
            "      margin-bottom: 20px;",
            "      background: #fff;",
            "    }",
            "    .question-header {",
            "      display: flex;",
            "      justify-content: space-between;",
            "      margin-bottom: 10px;",
            "      font-size: 13px;",
            "      color: var(--text-muted);",
            "    }",
            "    .question-statement {",
            "      font-size: 15px;",
            "      margin-bottom: 14px;",
            "      white-space: pre-line;",
            "    }",
            "    .options-list {",
            "      list-style-type: none;",
            "      padding-left: 0;",
            "      margin-bottom: 14px;",
            "    }",
            "    .options-list li {",
            "      padding: 4px 8px;",
            "      margin-bottom: 4px;",
            "      background: #f9fafb;",
            "      border-radius: 4px;",
            "      font-size: 14px;",
            "    }",
            "    .draft-box {",
            "      border: 1px dashed #9ca3af;",
            "      border-radius: 6px;",
            "      height: 90px;",
            "      padding: 10px;",
            "      font-family: monospace;",
            "      font-size: 12px;",
            "      color: #6b7280;",
            "      margin-top: 10px;",
            "      display: flex;",
            "      flex-direction: column;",
            "      justify-content: space-between;",
            "    }",
            "    table {",
            "      width: 100%;",
            "      border-collapse: collapse;",
            "      margin-top: 16px;",
            "      font-size: 13px;",
            "    }",
            "    th, td {",
            "      padding: 10px 12px;",
            "      border: 1px solid var(--border-color);",
            "      text-align: left;",
            "    }",
            "    th { background: #f3f4f6; font-weight: 600; }",
            "    tr:nth-child(even) { background: #f9fafb; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <div class='container'>",
            "    <div class='header'>",
            f"      <h1>🎯 OrientAI — Lista de Exercícios: {safe_topic}</h1>",
            "      <div class='meta-bar'>",
            f"        <span class='badge badge-track'>Trilha: {safe_track}</span>",
            f"        <span class='badge badge-target'>Meta: {int(exercise_list.target_accuracy * 100)}%</span>",
            f"        <span>Escopo: <em>{safe_scope}</em></span>",
            f"        <span>Gerado em: {created_str}</span>",
            "      </div>",
            "    </div>",
        ]

        for lvl in [1, 2, 3]:
            lvl_items = [e for e in exercise_list.exercises if e.level == lvl]
            if not lvl_items:
                continue
            icon_color = "var(--level1)" if lvl == 1 else ("var(--level2)" if lvl == 2 else "var(--level3)")
            html_parts.append(f"    <div class='section-title' style='color: {icon_color};'>")
            html_parts.append(f"      <span>●</span> {html.escape(lvl_items[0].level_name)}")
            html_parts.append("    </div>")

            for ex in lvl_items:
                html_parts.append("    <div class='question-card'>")
                html_parts.append("      <div class='question-header'>")
                html_parts.append(f"        <strong>Questão {html.escape(ex.id.upper())}</strong>")
                html_parts.append(f"        <span><em>{html.escape(ex.source or 'OrientAI')}</em></span>")
                html_parts.append("      </div>")
                html_parts.append(f"      <div class='question-statement'>{html.escape(ex.statement)}</div>")

                if ex.options:
                    html_parts.append("      <ul class='options-list'>")
                    for opt in ex.options:
                        html_parts.append(f"        <li>{html.escape(opt)}</li>")
                    html_parts.append("      </ul>")

                html_parts.append("      <div class='draft-box'>")
                html_parts.append("        <span>[Espaço para Dedução / Rascunho / Demonstração]</span>")
                html_parts.append("        <span>[ ] Resposta Final: ___________________________________________________________</span>")
                html_parts.append("      </div>")
                html_parts.append("    </div>")

        # Tabela de Gabarito
        html_parts.extend([
            "    <div class='page-break'></div>",
            "    <div class='section-title'>",
            "      <span>🔑</span> Gabarito Oficial & Critérios de Correção",
            "    </div>",
            "    <table>",
            "      <thead>",
            "        <tr>",
            "          <th style='width: 12%;'>Questão</th>",
            "          <th style='width: 10%;'>Nível</th>",
            "          <th style='width: 38%;'>Gabarito Oficial</th>",
            "          <th style='width: 40%;'>Critério / Justificativa</th>",
            "        </tr>",
            "      </thead>",
            "      <tbody>",
        ])

        for ex in exercise_list.exercises:
            html_parts.append("        <tr>")
            html_parts.append(f"          <td><strong>{html.escape(ex.id.upper())}</strong></td>")
            html_parts.append(f"          <td>N{ex.level}</td>")
            html_parts.append(f"          <td><strong>{html.escape(ex.answer_key)}</strong></td>")
            html_parts.append(f"          <td>{html.escape(ex.explanation or '-')}</td>")
            html_parts.append("        </tr>")

        html_parts.extend([
            "      </tbody>",
            "    </table>",
            "  </div>",
            "</body>",
            "</html>"
        ])

        return "\n".join(html_parts)

    def save_worksheet(
        self,
        exercise_list: ExerciseList,
        output_dir: Optional[Path] = None,
        generate_html: bool = True,
    ) -> Tuple[Path, Optional[Path]]:
        """Salva o entregável em data/worksheets/<track_id>_<topico_slug>.md e opcionalmente em .html."""
        dest_dir = output_dir or self.settings.resolved_worksheets_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        track_slug = self._slugify(exercise_list.track_id)
        topic_slug = self._slugify(exercise_list.topic_name)

        md_file = dest_dir / f"{track_slug}_{topic_slug}.md"
        md_content = self.build_markdown_worksheet(exercise_list)
        md_file.write_text(md_content, encoding="utf-8")

        html_file: Optional[Path] = None
        if generate_html:
            html_file = dest_dir / f"{track_slug}_{topic_slug}.html"
            html_content = self.build_html_worksheet(exercise_list)
            html_file.write_text(html_content, encoding="utf-8")

        return md_file, html_file
