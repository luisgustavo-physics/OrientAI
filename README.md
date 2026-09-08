# 🎯 OrientAI — Adaptive Multi-Track Study Agent & Dynamic Skill Trees

> **Agente Geral de Estudos de Alta Performance, Modular e Adaptativo baseado em Trilhas de Aprendizado (`Study Tracks`), Grafos Acíclicos Dirigidos (DAGs) de Habilidades, Agente Curricular com LLM e Ancoragem Cognitiva no NotebookLM.**

---

## 📌 1. Visão Geral: Por que o OrientAI?

Seja estudando para **vestibulares concorridos (Unicamp/Comvest)**, cursando **disciplinas universitárias de Computação/Engenharia**, ou conduzindo uma **trilha autodidata em Inteligência Artificial**, o maior inimigo do aprendizado profundo é a **ilusão de competência** e a **linearidade estática**.

O **OrientAI** converte tempo de estudo em **execução verificável e progressão topológica**:
- **Trilhas em Grafo Acíclico Dirigido (DAG):** Mapeamento de tópicos com pré-requisitos rígidos, desbloqueio progressivo e verificação formal contra ciclos.
- **Agente Curricular Especialista (`CurriculumAgent`):** Algoritmo/LLM que gera cadeias otimizadas de tópicos a partir de um ponto de origem e destino (ex.: *Teoria da Computação* $\to$ *Criptografia Moderna*), expandindo o grafo dinamicamente conforme novos nós são dominados.
- **Ancoragem Cognitiva no NotebookLM:** Cada trilha é associada a um caderno (`notebook_id`) com fontes especializadas indexadas, gerando briefings de estudo focados para cada nó.
- **Regra Anti-Passividade:** Nenhum bloco de estudo é puramente teórico. Toda sessão exige um **entregável tangível** (código com testes, exercícios resolvidos com taxa de acerto $\ge 80\%$, resoluções discursivas formalizadas).
- **Agendamento Otimizado por Gaps:** O algoritmo agenda apenas tópicos desbloqueados (`UNLOCKED` ou `IN_PROGRESS`), priorizando gaps históricos e metas semanais.
- **Proteção da Rotina Real:** Os blocos são alocados exclusivamente nos intervalos livres entre compromissos fixos (refeições, treinos, sono, trabalho).
- **Sincronização com Anki:** Integração direta com AnkiConnect local com fila de contingência offline automática (`data/anki_queue.json`).

---

## 🗂️ 2. O Conceito de Trilhas de Estudo (`tracks/`) e DAGs

Uma **Trilha de Estudo (`StudyTrack`)** pode ser tanto declarativa/plana quanto estruturada em **Grafo (DAG)**:
- Identificador (`id`), nome e objetivos.
- Prazo alvo opcional (`target_date`) para contagem regressiva e cálculo de urgência.
- Caderno ancorado no **NotebookLM** (`notebook_id` e `notebook_sources`).
- Grafo de tópicos (`nodes: Dict[str, TopicNode]`), onde cada nó possui:
  - `id`, `name`, `subject`.
  - `prerequisites`: Lista de nós que devem atingir `MASTERED` para que este nó seja desbloqueado.
  - `mastery_threshold`: Limiar de acerto (padrão 80%) para conclusão do nó.
  - `status`: `LOCKED`, `UNLOCKED`, `IN_PROGRESS` ou `MASTERED`.
  - `deliverable_template`: Requisito prático obrigatório para comprovação de domínio.

```
OrientAI/
└── tracks/
    ├── autodidata_ia.json         # Deep Learning, LLMs/RAG, MLOps
    ├── comvest.json               # Matriz oficial Comvest (Filosofia/Sociologia) + DAG Matemática/Física
    └── faculdade_computacao.json  # Algoritmos, Cálculo, Sistemas Operacionais
```

---

## 🏛️ 3. Arquitetura do Sistema

```mermaid
flowchart TD
    subgraph Knowledge Base
        NLM["NotebookLM (1 Notebook por Trilha + Fontes Especializadas)"]
    end

    subgraph Curriculum Specialist
        CA["CurriculumAgent (Geração Guiada & Expansão)"]
        CA -->|Origem -> Destino| NODES["Geração de Nós Intermediários"]
        CA -->|Associa Fontes/Referências| NLM
    end

    subgraph Dynamic Graph Engine
        GE["core/graph_engine.py (Topologia DAG & Desbloqueio)"]
        NODES --> GE
        GE -->|Nó Dominado (Mastery >= 80% + Entregável)| RETRO["Retroalimentação: Expansão do Grafo"]
        RETRO --> CA
    end

    subgraph Scheduler & Verification
        SCHED["core/scheduler.py (Aloca Apenas UNLOCKED / IN_PROGRESS)"]
        GE --> SCHED
        SL["StudyLog (Métricas & Entregáveis Tangíveis)"] --> GE
    end
```

---

## 🚀 4. Instalação e Início Rápido

### 4.1. Configuração do Ambiente

```bash
cd OrientAI

# Criar e ativar ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependências
.venv/bin/pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
```

### 4.2. Execução dos Testes Unitários

```bash
.venv/bin/pytest -v
```
*(28 testes unitários cobrindo Curadoria de Exercícios, Google Docs, DAGs, validação de ciclos, CurriculumAgent, NotebookLM, Scheduler, Métricas e Anki).*


---

## 💻 5. Guia Completo de Uso da CLI

### 🌳 1. Visualizar Árvore de Habilidades em Grafo (`track tree`)

Renderiza a topologia do grafo da trilha via terminal com cores e ícones de status (`DOMINADO`, `DESBLOQUEADO`, `BLOQUEADO`):

```bash
python main.py track tree --track comvest
```

### ✨ 2. Gerar Trilha Guiada com o Agente Curricular (`track generate`)

Gera uma nova trilha em grafo do zero a partir de um ponto de origem e um destino:

```bash
python main.py track generate \
  --name "Teoria da Computação até Criptografia" \
  --from "Teoria da Computação" \
  --to "Criptografia Moderna"
```

### 📄 3. Curadoria de Exercícios e Integração Google Docs (`sheet generate`)

Gera listas pedagógicas estruturadas em 3 níveis (Básico, Intermediário e Avançado) exportando diretamente para o Google Docs (com fallback gracioso em Markdown):

```bash
# Curadoria padrão para banca Comvest / Unicamp
python main.py sheet generate \
  --topic "Geometria Analítica: Cônicas" \
  --track comvest

# Curadoria universitária para cálculo
python main.py sheet generate \
  --topic "Cálculo: Integrais Definidas" \
  --track faculdade_computacao \
  --scope "Livros Universitários (Guidorizzi / Stewart / Leithold)"
```

### 📅 4. Gerar o Plano de Estudos do Dia (`plan today`)

O agendador aloca apenas nós **desbloqueados** ou **em andamento**:

```bash
# Plano balanceado entre TODAS as trilhas ativas
python main.py plan today

# Plano focado na trilha Comvest
python main.py plan today --track comvest
```

### 📝 5. Registrar Execução Prática e Desbloquear Nós (`log`)

Ao atingir precisão $\ge 80\%$ e confirmar o entregável tangível, o OrientAI atualiza o nó para `MASTERED` e desbloqueia automaticamente os nós sucessores no grafo:

```bash
python main.py log \
  --track comvest \
  --subject mat_trigo_fund \
  --metric 9/10 \
  --deliverable "Resolver lista de 8 exercícios de arcos e identidades fundamentais" \
  --minutes 50
```

### 📚 6. Gerenciar Trilhas Tradicionais (`track list`, `track toggle`)


```bash
# Listar todas as trilhas disponíveis
python main.py track list

# Ativar ou desativar uma trilha específica
python main.py track toggle --id comvest
```

### 🗂️ 6. Flashcards no Anki (`card`)

```bash
python main.py card --deck "Vestibular::Matematica" \
  --front "Qual a relação fundamental da trigonometria?" \
  --back "sen²(x) + cos²(x) = 1"
```

### 📑 7. Relatórios Analíticos (`report`)

```bash
python main.py report
python main.py report --weekly
```
