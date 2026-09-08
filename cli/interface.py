"""Interface CLI rica para o OrientAI com suporte a Multi-Trilhas, Grafos DAG e NotebookLM."""

import argparse
from datetime import date, datetime
import sys
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from config.settings import Settings, get_settings
from core.curriculum import CurriculumAgent
from core.exercise_curator import ExerciseCurator
from core.graph_engine import GraphEngine
from core.metrics import MetricsEngine
from core.models import StudyLog, StudyTrack, SubjectConfig, TopicNode, TopicStatus
from core.scheduler import StudyScheduler
from core.state import StateManager
from core.tracks import TrackManager
from integrations.anki_sync import AnkiClient
from integrations.gdocs_client import GoogleDocsClient
from integrations.notebooklm import NotebookLMClient

console = Console()



def render_banner(settings: Settings, track_manager: Optional[TrackManager] = None) -> None:
    """Renderiza o banner de cabeçalho do OrientAI com dados das trilhas ativas."""
    tm = track_manager or TrackManager(settings)
    today = date.today()
    active_tracks = tm.get_active_tracks()

    banner_text = Text()
    banner_text.append("🎯 ORIENTAI ", style="bold cyan")
    banner_text.append("• Adaptive Multi-Track Study Agent\n", style="bold white")
    banner_text.append(f"📅 Data: {today.strftime('%d/%m/%Y')} | ", style="dim")
    banner_text.append(f"📚 Trilhas Ativas: {len(active_tracks)} | ", style="bold green")

    closest_deadline = None
    closest_track_name = None
    for t in active_tracks:
        if t.target_date:
            try:
                t_dt = datetime.strptime(t.target_date, "%Y-%m-%d").date()
                diff = (t_dt - today).days
                if diff >= 0 and (closest_deadline is None or diff < closest_deadline):
                    closest_deadline = diff
                    closest_track_name = t.name
            except ValueError:
                pass

    if closest_deadline is not None:
        banner_text.append(f"⏳ Próximo Alvo ({closest_track_name}): {closest_deadline} dias\n", style="bold yellow")
    else:
        banner_text.append("⏳ Sem prazo fixo configurado\n", style="dim")

    tracks_names = ", ".join(t.name for t in active_tracks[:3])
    if len(active_tracks) > 3:
        tracks_names += f" (+{len(active_tracks) - 3})"
    banner_text.append(f"🎯 Foco Atual: {tracks_names or 'Nenhuma trilha ativa'}", style="dim magenta")

    console.print(Panel(banner_text, border_style="cyan", padding=(0, 1)))


def handle_track_list(args: argparse.Namespace) -> None:
    """Lista todas as trilhas de estudo instaladas no repositório."""
    settings = get_settings()
    tm = TrackManager(settings)
    render_banner(settings, tm)

    tracks = tm.load_all_tracks()
    if not tracks:
        console.print("[yellow]Nenhuma trilha encontrada em tracks/.[/yellow]")
        return

    table = Table(title="Trilhas de Estudo Instaladas", border_style="cyan", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="bold yellow", width=22)
    table.add_column("Nome da Trilha", style="bold white", min_width=30)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Disciplinas", justify="center", width=12)
    table.add_column("Nós (DAG)", justify="center", width=10)
    table.add_column("NotebookLM", style="dim cyan", width=18)
    table.add_column("Prazo Alvo", justify="center", width=18)

    today = date.today()
    for t_id, track in tracks.items():
        status_str = "[bold green]ATIVA[/bold green]" if track.is_active else "[dim red]INATIVA[/dim red]"
        deadline_str = "N/A"
        if track.target_date:
            try:
                t_dt = datetime.strptime(track.target_date, "%Y-%m-%d").date()
                diff = (t_dt - today).days
                deadline_str = f"{track.target_date} ({diff}d)" if diff >= 0 else f"{track.target_date} (expirado)"
            except ValueError:
                deadline_str = track.target_date

        table.add_row(
            track.id,
            track.name,
            status_str,
            str(len(track.subjects)),
            str(len(track.nodes)),
            track.notebook_id or "Não vinculado",
            deadline_str
        )

    console.print(table)
    console.print("\n[dim]💡 Dica: Visualize o grafo com [bold cyan]python main.py track tree --track <id>[/bold cyan].[/dim]")


def handle_track_tree(args: argparse.Namespace) -> None:
    """Exibe a árvore visual de habilidades e pré-requisitos em formato de DAG."""
    settings = get_settings()
    tm = TrackManager(settings)
    track_id = args.track.strip() if args.track else None

    if not track_id:
        active = tm.get_active_tracks()
        if active:
            track_id = active[0].id
        else:
            console.print("[bold red]Erro:[/bold red] Especifique uma trilha com --track <id>.")
            sys.exit(1)

    track = tm.get_track(track_id)
    if not track:
        console.print(f"[bold red]Erro:[/bold red] Trilha '{track_id}' não encontrada.")
        sys.exit(1)

    GraphEngine.initialize_track_graph(track)

    root_tree = Tree(f"🌳 [bold white]{track.name}[/bold white] [dim]({track.id})[/dim]")
    if track.notebook_id:
        root_tree.add(f"📓 [cyan]NotebookLM:[/cyan] {track.notebook_id}")

    if not track.nodes:
        console.print(Panel(f"A trilha '{track.name}' não possui nós de grafo cadastrados (modo disciplinas planas).", border_style="yellow"))
        return

    # Agrupa nós por disciplina
    by_subject: dict[str, list[TopicNode]] = {}
    for node in track.nodes.values():
        by_subject.setdefault(node.subject, []).append(node)

    for subject, nodes in by_subject.items():
        sub_branch = root_tree.add(f"📚 [bold magenta]{subject}[/bold magenta]")

        for node in nodes:
            # Badges de status
            if node.status == TopicStatus.MASTERED:
                badge = "[bold green]✅ DOMINADO[/bold green]"
            elif node.status == TopicStatus.IN_PROGRESS:
                badge = f"[bold cyan]⏳ EM ANDAMENTO ({node.current_accuracy*100:.0f}%)[/bold cyan]"
            elif node.status == TopicStatus.UNLOCKED:
                badge = "[bold yellow]🔓 DESBLOQUEADO[/bold yellow]"
            else:
                badge = "[dim red]🔒 BLOQUEADO[/dim red]"

            prereq_str = f" [dim](Pré-requisitos: {', '.join(node.prerequisites)})[/dim]" if node.prerequisites else " [dim](Raiz - Sem pré-requisitos)[/dim]"
            node_label = f"{badge} [bold white]{node.name}[/bold white]{prereq_str}"
            node_branch = sub_branch.add(node_label)

            if node.deliverable_template:
                node_branch.add(f"[italic dim]🎯 Entregável: {node.deliverable_template}[/italic dim]")
            if node.notebook_ref:
                node_branch.add(f"[dim cyan]📌 Ref: {node.notebook_ref}[/dim cyan]")

    console.print(root_tree)


def handle_track_generate(args: argparse.Namespace) -> None:
    """Gera uma trilha estruturada em grafo conectando nó de origem ao destino."""
    settings = get_settings()
    tm = TrackManager(settings)
    agent = CurriculumAgent()

    name = args.name.strip() if args.name else None
    origin = getattr(args, "from_node", None)
    destination = getattr(args, "to_node", None)
    prompt = args.prompt.strip() if args.prompt else None
    notebook_id = args.notebook_id.strip() if getattr(args, "notebook_id", None) else None
    target_date = args.target_date.strip() if getattr(args, "target_date", None) else None

    if not name:
        console.print("[bold red]Erro:[/bold red] O parâmetro --name é obrigatório.")
        sys.exit(1)

    if not origin:
        origin = "Fundamentos Conceituais"
    if not destination:
        destination = name

    track_id = args.id.strip() if getattr(args, "id", None) else name.lower().replace(" ", "_")

    with console.status(f"[bold green]Projetando grafo curricular de '{origin}' até '{destination}'...[/bold green]"):
        track = agent.generate_guided_curriculum(
            track_id=track_id,
            name=name,
            origin=origin,
            destination=destination,
            prompt=prompt,
            notebook_id=notebook_id,
            target_date=target_date
        )
        saved_path = tm.save_track(track)

    console.print(f"\n[bold green]✨ Trilha em Grafo Gerada com Sucesso![/bold green]")
    console.print(f"📁 Arquivo: [cyan]{saved_path}[/cyan]")
    console.print(f"🏁 Origem: [bold yellow]{origin}[/bold yellow] ➔ Destino: [bold green]{destination}[/bold green]")
    console.print(f"📓 NotebookLM ID: [cyan]{track.notebook_id}[/cyan]\n")

    # Exibe a árvore gerada
    args.track = track.id
    handle_track_tree(args)


def handle_track_toggle(args: argparse.Namespace) -> None:
    """Ativa ou desativa uma trilha."""
    settings = get_settings()
    tm = TrackManager(settings)
    track_id = args.id.strip()

    track = tm.get_track(track_id)
    if not track:
        console.print(f"[bold red]Erro:[/bold red] Trilha '{track_id}' não encontrada em tracks/.")
        sys.exit(1)

    tm.toggle_track(track_id)
    updated = tm.get_track(track_id)
    new_status = "[bold green]ATIVA[/bold green]" if updated and updated.is_active else "[bold red]INATIVA[/bold red]"
    console.print(f"✨ Trilha [bold yellow]{track_id}[/bold yellow] agora está {new_status}!")


def handle_track_create(args: argparse.Namespace) -> None:
    """Cria uma nova trilha de estudo a partir dos argumentos ou modo rápido."""
    settings = get_settings()
    tm = TrackManager(settings)

    track_id = args.id.strip().lower().replace(" ", "_") if args.id else None
    name = args.name.strip() if args.name else None
    desc = args.desc.strip() if args.desc else "Trilha de estudos personalizada"
    target_date = args.target_date.strip() if args.target_date else None

    if not track_id or not name:
        console.print("[bold cyan]=== Assistente de Criação de Trilha ===[/bold cyan]")
        try:
            if not track_id:
                track_id = input("ID único da trilha (ex: mestrado_ia, concurso_bacen): ").strip().lower().replace(" ", "_")
            if not name:
                name = input("Nome completo da trilha: ").strip()
            if not args.desc:
                user_desc = input("Descrição da trilha (opcional): ").strip()
                if user_desc:
                    desc = user_desc
            if not target_date:
                user_date = input("Data alvo (YYYY-MM-DD, opcional): ").strip()
                if user_date:
                    target_date = user_date
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Criação cancelada.[/dim]")
            return

    if not track_id or not name:
        console.print("[bold red]Erro:[/bold red] ID e Nome são obrigatórios.")
        sys.exit(1)

    new_track = StudyTrack(
        id=track_id,
        name=name,
        description=desc,
        target_date=target_date,
        is_active=True,
        subjects={}
    )

    path = tm.create_track(new_track)
    console.print(f"\n[bold green]✅ Trilha '{name}' criada com sucesso![/bold green]")
    console.print(f"Arquivo salvo em: [cyan]{path}[/cyan]")


def handle_plan_today(args: argparse.Namespace) -> None:
    """Gera e exibe o plano de estudos objetivo do dia."""
    settings = get_settings()
    tm = TrackManager(settings)
    scheduler = StudyScheduler(settings, track_manager=tm)
    
    render_banner(settings, tm)

    target_track = args.track.strip() if args.track else None
    with console.status("[bold green]Otimizando blocos e balanceando prioridades entre trilhas e grafos...[/bold green]"):
        try:
            plan = scheduler.generate_daily_plan(track_id=target_track)
        except Exception as e:
            console.print(f"[bold red]Erro ao gerar plano:[/bold red] {e}")
            sys.exit(1)

    console.print(f"\n[bold white]📋 PLANO DO DIA — {plan.date}[/bold white]")
    console.print(f"[dim italic]{plan.focus_summary}[/dim italic]\n")

    table = Table(title="Sessões de Foco Tangível (Anti-Passividade)", border_style="blue", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="bold yellow", width=5)
    table.add_column("Horário", style="cyan", width=13)
    table.add_column("Trilha", style="magenta", width=16)
    table.add_column("Disciplina / Tópico", style="bold white", width=28)
    table.add_column("Atividade", style="green", width=14)
    table.add_column("Entregável Tangível Obrigatório", style="white")
    table.add_column("Auditável", justify="center", width=11)

    for block in plan.blocks:
        verif = "[bold red]SIM (Obrigatório)[/bold red]" if block.requires_tangible else "[dim]Prático[/dim]"
        act_name = block.activity_type.value.upper()
        table.add_row(
            block.id,
            f"{block.start_time} - {block.end_time}",
            block.track_id,
            block.subject_name,
            act_name,
            block.deliverable,
            verif
        )

    console.print(table)

    if plan.commitments_accounted:
        commitments_str = " • ".join(plan.commitments_accounted)
        console.print(f"\n[dim]🛡️  [bold]Compromissos Fixos Protegidos:[/bold] {commitments_str}[/dim]")

    console.print(f"[dim]⏱️  Tempo total planejado em ação: [bold]{plan.total_planned_minutes} min[/bold][/dim]")
    console.print("\n[bold green]💡 Regra Anti-Passividade:[/bold green] Nunca estude sem produzir código, lista de exercícios ou flashcards.")


def handle_log(args: argparse.Namespace) -> None:
    """Registra o resultado prático de uma sessão de estudo atrelada a uma trilha e nó do grafo."""
    settings = get_settings()
    state_manager = StateManager(settings)
    tm = TrackManager(settings)
    metrics_engine = MetricsEngine(settings, state_manager, track_manager=tm)
    curriculum_agent = CurriculumAgent()

    raw_metric = args.metric.strip()
    if "/" not in raw_metric:
        console.print("[bold red]Erro:[/bold red] O parâmetro --metric deve estar no formato acertos/total (ex: --metric 8/10).")
        sys.exit(1)

    try:
        parts = raw_metric.split("/")
        correct = int(parts[0])
        total = int(parts[1])
        if total <= 0 or correct < 0 or correct > total:
            raise ValueError
    except ValueError:
        console.print("[bold red]Erro:[/bold red] Valores inválidos para acertos/total. Exemplo válido: --metric 7/10")
        sys.exit(1)

    subject_input = args.subject.lower().strip()
    track_id = args.track.strip() if args.track else None
    topic_id = getattr(args, "topic", None)

    # Identifica trilha
    if not track_id:
        found = tm.find_subject_track(subject_input)
        if found:
            track, sub_conf = found
            track_id = track.id
            canonical_subject = sub_conf.name
        else:
            actives = tm.get_active_tracks()
            track_id = actives[0].id if len(actives) == 1 else "geral"
            canonical_subject = subject_input.title()
    else:
        track = tm.get_track(track_id)
        if track:
            # Verifica se subject_input é um nó do grafo
            if subject_input in track.nodes:
                topic_id = subject_input
                canonical_subject = track.nodes[subject_input].name
            else:
                sub = track.get_subject(subject_input)
                canonical_subject = sub.name if sub else subject_input.title()
        else:
            canonical_subject = subject_input.title()

    # Se a trilha existe e possui nós de grafo, verifica correspondência de tópico
    track = tm.get_track(track_id)
    unlocked_nodes = []
    became_mastered = False
    newly_expanded_node = None

    if track and track.nodes:
        matched_node_id = topic_id
        if not matched_node_id:
            for n_id, n in track.nodes.items():
                if n_id.lower() == subject_input or n.name.lower() == subject_input:
                    matched_node_id = n_id
                    break

        if matched_node_id and matched_node_id in track.nodes:
            topic_id = matched_node_id
            became_mastered, unlocked_nodes = GraphEngine.update_topic_progress(
                track=track,
                topic_id=topic_id,
                correct=correct,
                total=total,
                deliverable_done=not args.failed_deliverable
            )
            # Verifica expansão dinâmica do currículo (retroalimentação)
            if became_mastered:
                newly_expanded_node = curriculum_agent.check_and_expand_curriculum(track)

            tm.save_track(track)

    accuracy = round(correct / total, 4)
    minutes = args.minutes if args.minutes else settings.pomodoro_work_minutes
    today_str = date.today().strftime("%Y-%m-%d")
    log_id = f"log_{int(datetime.now().timestamp())}"

    log = StudyLog(
        id=log_id,
        track_id=track_id,
        topic_id=topic_id,
        date=today_str,
        subject=canonical_subject,
        correct_answers=correct,
        total_questions=total,
        accuracy_rate=accuracy,
        minutes_spent=minutes,
        deliverable_completed=not args.failed_deliverable,
        deliverable_description=args.deliverable,
        notes=args.notes
    )

    state_manager.add_log(log)
    metrics_engine.generate_daily_report()

    pct = accuracy * 100
    color = "green" if pct >= 75 else ("yellow" if pct >= 50 else "red")
    
    panel_content = Text()
    panel_content.append(f"✅ Sessão de {canonical_subject} (Trilha: {track_id}) registrada!\n", style="bold green")
    if topic_id:
        panel_content.append(f"• Nó de Habilidade (DAG): {topic_id}\n", style="cyan")
    panel_content.append(f"• Desempenho: {correct}/{total} ({pct:.1f}% de precisão)\n", style=f"bold {color}")
    panel_content.append(f"• Tempo dedicado: {minutes} minutos\n", style="white")
    panel_content.append(f"• Entregável cumprido: {'SIM' if log.deliverable_completed else 'NÃO'}\n", style="white")
    if log.deliverable_description:
        panel_content.append(f"• Entregável: {log.deliverable_description}\n", style="dim")

    console.print(Panel(panel_content, title="Registro de Execução Concluído", border_style=color))

    # Alerta de desbloqueio em caso de maestria
    if became_mastered:
        unlock_text = Text()
        unlock_text.append(f"🎉 MAESTRIA ALCANÇADA NO NÓ '{topic_id}'!\n", style="bold green")
        if unlocked_nodes:
            unlock_text.append(f"🔓 Novos Nós Desbloqueados: {', '.join(unlocked_nodes)}\n", style="bold yellow")
        if newly_expanded_node:
            unlock_text.append(f"🔄 Retroalimentação Curricular: Nó de aprofundamento gerado: '{newly_expanded_node.name}'\n", style="bold cyan")
        console.print(Panel(unlock_text, border_style="green"))


def handle_status(args: argparse.Namespace) -> None:
    """Exibe painel visual completo de status, gaps e métricas acumuladas por trilha."""
    settings = get_settings()
    state_manager = StateManager(settings)
    tm = TrackManager(settings)
    metrics_engine = MetricsEngine(settings, state_manager, track_manager=tm)
    anki_client = AnkiClient(settings)

    render_banner(settings, tm)

    daily_metrics = metrics_engine.get_daily_metrics()
    weekly_metrics = metrics_engine.get_weekly_metrics()
    anki_stats = anki_client.get_today_stats()

    summary_text = Text()
    summary_text.append(f"Hoje: {daily_metrics['minutes_spent']} min estudados ({daily_metrics['time_adherence_percent']}% da meta diária)\n")
    summary_text.append(f"Exercícios no dia: {daily_metrics['total_questions']} (Acertos: {daily_metrics['correct_answers']} • {daily_metrics['overall_accuracy']*100:.1f}%)\n")
    anki_status_label = "[green]ONLINE[/green]" if anki_stats["online"] else "[yellow]OFFLINE (fila local ativa)[/yellow]"
    summary_text.append(f"AnkiConnect: {anki_status_label} • Cards revisados hoje: {anki_stats['reviewed_today']} • Pendentes: {anki_stats['total_pending']}")

    console.print(Panel(summary_text, title="📊 Status do Dia", border_style="blue"))

    target_track = args.track.strip() if hasattr(args, "track") and args.track else None
    tracks_to_show = weekly_metrics.get("tracks", {})

    if target_track and target_track in tracks_to_show:
        tracks_to_show = {target_track: tracks_to_show[target_track]}

    for t_id, track_info in tracks_to_show.items():
        if not track_info.get("is_active") and not target_track:
            continue

        deadline_info = f" • Prazo: {track_info['days_remaining']} dias restantes" if track_info.get("days_remaining") is not None else ""
        table = Table(title=f"🎯 Metas Semanais — {track_info['name']}{deadline_info}", border_style="cyan")
        table.add_column("Disciplina", style="bold white", width=24)
        table.add_column("Peso", justify="center", style="yellow", width=8)
        table.add_column("Progresso Semanal", style="cyan", width=20)
        table.add_column("Taxa Acerto", justify="center", width=12)
        table.add_column("Tempo", justify="center", width=12)
        table.add_column("Status / Ação", width=22)

        subjects_data = track_info.get("subjects", {})
        for sub_id, data in subjects_data.items():
            q_done = data["questions_solved"]
            goal = data["goal"]
            pct = data["goal_progress_percent"]
            acc = data["accuracy"]
            acc_pct = f"{acc * 100:.1f}%" if q_done > 0 else "N/A"

            bar_len = 10
            filled = min(bar_len, int((pct / 100) * bar_len))
            bar = "█" * filled + "░" * (bar_len - filled)
            progress_str = f"{bar} {q_done}/{goal}"

            if q_done == 0:
                action = "[bold red]⚠️  Pendente esta semana[/bold red]"
            elif acc < 0.60:
                action = "[bold yellow]🔍 Reforçar prática/erros[/bold yellow]"
            elif pct >= 100:
                action = "[bold green]✅ Meta atingida![/bold green]"
            else:
                action = "[cyan]🔄 Em progresso[/cyan]"

            acc_style = "green" if acc >= 0.75 else ("yellow" if acc >= 0.55 else "red")

            table.add_row(
                data["name"],
                f"{data['weight']}x",
                progress_str,
                f"[{acc_style}]{acc_pct}[/{acc_style}]",
                f"{data['minutes_spent']} min",
                action
            )

        console.print(table)


def handle_card(args: argparse.Namespace) -> None:
    """Cria um flashcard rápido no Anki para fixação imediata."""
    settings = get_settings()
    anki_client = AnkiClient(settings)

    deck = args.deck.strip()
    front = args.front.strip()
    back = args.back.strip()

    result = anki_client.create_card(deck_name=deck, front=front, back=back)
    
    if result.get("offline"):
        console.print(f"[bold yellow]⚠️  Anki offline:[/bold yellow] {result['message']}")
    else:
        console.print(f"[bold green]✨ Card adicionado:[/bold green] {result['message']}")


def handle_report(args: argparse.Namespace) -> None:
    """Gera relatórios consolidados em JSON e Markdown."""
    settings = get_settings()
    metrics_engine = MetricsEngine(settings)

    if args.weekly:
        j_path, m_path = metrics_engine.generate_weekly_report()
        console.print(f"[bold green]Relatório semanal gerado com sucesso![/bold green]")
    else:
        j_path, m_path = metrics_engine.generate_daily_report()
        console.print(f"[bold green]Relatório diário gerado com sucesso![/bold green]")

    console.print(f"📄 Markdown: [cyan]{m_path}[/cyan]")
    console.print(f"📊 JSON: [cyan]{j_path}[/cyan]")


def handle_sheet_generate(args: argparse.Namespace) -> None:
    """Gera uma lista de exercícios curada em 3 níveis e exporta para o Google Docs (com fallback local em Markdown)."""
    settings = get_settings()
    tm = TrackManager(settings)
    curator = ExerciseCurator()
    gdocs = GoogleDocsClient()

    topic_name = args.topic.strip() if args.topic else None
    track_id = args.track.strip() if args.track else None
    source_scope = args.scope.strip() if getattr(args, "scope", None) else None

    if not topic_name:
        console.print("[bold red]Erro:[/bold red] O parâmetro --topic é obrigatório.")
        sys.exit(1)

    if not track_id:
        active = tm.get_active_tracks()
        if active:
            track_id = active[0].id
        else:
            track_id = "geral"

    with console.status(f"[bold green]Curando questões pedagógicas e estruturando lista para '{topic_name}' ({track_id})...[/bold green]"):
        exercise_list = curator.curate_exercise_list(
            topic_name=topic_name,
            track_id=track_id,
            source_scope=source_scope
        )

    title = f"OrientAI — Lista de Exercícios: {topic_name} ({track_id.upper()})"

    with console.status("[bold green]Criando documento estilizado no Google Docs...[/bold green]"):
        result_url_or_path = gdocs.create_exercise_doc(title=title, exercise_list=exercise_list)

    is_remote = result_url_or_path.startswith("http")

    panel_text = Text()
    panel_text.append("✨ Lista de Exercícios Tangíveis Gerada com Sucesso!\n\n", style="bold green")
    panel_text.append(f"📚 Tópico: {exercise_list.topic_name}\n", style="bold white")
    panel_text.append(f"🎯 Trilha: {exercise_list.track_id}\n", style="cyan")
    panel_text.append(f"🔍 Escopo de Fontes: {exercise_list.source_scope}\n", style="dim")
    panel_text.append(f"📊 Composição: 3 N1 (Básico) + 4 N2 (Intermediário) + 3 N3 (Avançado) = 10 Questões\n", style="yellow")
    panel_text.append(f"🎯 Meta de Acertos: {int(exercise_list.target_accuracy * 100)}% (Anti-Passividade)\n\n", style="bold magenta")

    if is_remote:
        panel_text.append("📄 Google Docs Criado:\n", style="bold white")
        panel_text.append(f"🔗 {result_url_or_path}\n", style="bold underline cyan")
    else:
        panel_text.append("📂 Fallback Local Ativado (Credenciais Google não detectadas):\n", style="bold yellow")
        panel_text.append(f"📄 Arquivo Markdown: {result_url_or_path}\n\n", style="bold underline green")
        panel_text.append("💡 Dica: Para criar diretamente no Google Drive, configure o arquivo 'credentials.json'.\n", style="dim")

    console.print(Panel(panel_text, title="🎯 OrientAI • Curador de Exercícios", border_style="cyan"))


def build_parser() -> argparse.ArgumentParser:
    """Constrói o parser de comandos de linha de comando."""
    parser = argparse.ArgumentParser(
        prog="orientai",
        description="OrientAI: Agente Adaptativo de Estudos baseado em Trilhas e Grafos DAG."
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    # Comando 'track'
    track_parser = subparsers.add_parser("track", help="Gerenciador de Trilhas e Grafos de Estudo")
    track_sub = track_parser.add_subparsers(dest="track_action")
    
    # track list
    track_sub.add_parser("list", help="Lista todas as trilhas disponíveis e seu status")

    # track tree
    track_tree = track_sub.add_parser("tree", help="Visualiza o grafo de tópicos e árvore de habilidades")
    track_tree.add_argument("--track", "-k", help="ID da trilha para exibir a árvore")

    # track generate
    track_gen = track_sub.add_parser("generate", help="Gera uma trilha em grafo guiada por nó de destino")
    track_gen.add_argument("--name", "-n", required=True, help="Nome descritivo da trilha")
    track_gen.add_argument("--id", "-i", help="ID único da trilha")
    track_gen.add_argument("--from", dest="from_node", help="Nó de partida (Origem)")
    track_gen.add_argument("--to", dest="to_node", help="Nó final (Destino)")
    track_gen.add_argument("--prompt", "-p", help="Descrição livre ou lista de tópicos a cobrir")
    track_gen.add_argument("--notebook-id", help="ID do caderno do NotebookLM associado")
    track_gen.add_argument("--target-date", help="Data alvo (YYYY-MM-DD)")
    
    # track create
    track_create = track_sub.add_parser("create", help="Cria uma nova trilha de estudo")
    track_create.add_argument("--id", "-i", help="ID único da trilha (ex: mestrado_ia)")
    track_create.add_argument("--name", "-n", help="Nome descritivo da trilha")
    track_create.add_argument("--desc", "-d", help="Descrição dos objetivos")
    track_create.add_argument("--target-date", help="Data alvo (YYYY-MM-DD)")

    # track toggle
    track_toggle = track_sub.add_parser("toggle", help="Ativa ou desativa uma trilha")
    track_toggle.add_argument("--id", "-i", required=True, help="ID da trilha para alternar status")

    # Comando 'plan'
    plan_parser = subparsers.add_parser("plan", help="Gerenciador de planos de estudo")
    plan_sub = plan_parser.add_subparsers(dest="plan_target")
    plan_today = plan_sub.add_parser("today", help="Gera o plano do dia balanceado")
    plan_today.add_argument("--track", "-k", help="Foca exclusivamente nesta trilha de estudo")

    # Comando 'log'
    log_parser = subparsers.add_parser("log", help="Registra resultado prático de uma sessão")
    log_parser.add_argument("--subject", "-s", required=True, help="Disciplina ou nó de tópico estudado")
    log_parser.add_argument("--metric", "-m", required=True, help="Acertos/Total de exercícios (ex: 8/10)")
    log_parser.add_argument("--track", "-k", help="ID da trilha correspondente")
    log_parser.add_argument("--topic", help="ID do nó de tópico no grafo (DAG)")
    log_parser.add_argument("--minutes", "-t", type=int, default=50, help="Tempo gasto em minutos (padrão: 50)")
    log_parser.add_argument("--deliverable", "-d", help="Descrição do entregável tangível produzido")
    log_parser.add_argument("--notes", "-n", help="Observações sobre dificuldades ou insights")
    log_parser.add_argument("--failed-deliverable", action="store_true", help="Marca que o entregável não foi concluído")

    # Comando 'status'
    status_parser = subparsers.add_parser("status", help="Exibe painel de progresso, gaps e aderência")
    status_parser.add_argument("--track", "-k", help="Filtra a visualização para uma trilha específica")

    # Comando 'sheet'
    sheet_parser = subparsers.add_parser("sheet", help="Curadoria de exercícios e geração de listas no Google Docs")
    sheet_sub = sheet_parser.add_subparsers(dest="sheet_action")
    sheet_gen = sheet_sub.add_parser("generate", help="Gera lista de exercícios nos 3 níveis pedagógicos")
    sheet_gen.add_argument("--topic", "-t", required=True, help="Nome do tópico ou habilidade")
    sheet_gen.add_argument("--track", "-k", required=True, help="ID da trilha de estudo")
    sheet_gen.add_argument("--scope", "-s", help="Escopo das questões / fontes (opcional)")

    # Comando 'card'
    card_parser = subparsers.add_parser("card", help="Cria flashcard de fixação no Anki")
    card_parser.add_argument("--deck", required=True, help="Nome do deck no Anki")
    card_parser.add_argument("--front", "-f", required=True, help="Pergunta ou conceito frontal")
    card_parser.add_argument("--back", "-b", required=True, help="Resposta direta e precisa")

    # Comando 'report'
    report_parser = subparsers.add_parser("report", help="Exporta relatórios analíticos")
    report_parser.add_argument("--weekly", "-w", action="store_true", help="Gera relatório semanal comparativo")

    return parser


def run_cli() -> None:
    """Ponto de entrada principal da CLI."""
    parser = build_parser()
    
    argv = sys.argv[1:]
    if argv and argv[0] == "study":
        argv = argv[1:]

    if not argv:
        parser.print_help()
        return

    args = parser.parse_args(argv)

    if args.command == "track":
        if args.track_action == "list" or not args.track_action:
            handle_track_list(args)
        elif args.track_action == "tree":
            handle_track_tree(args)
        elif args.track_action == "generate":
            handle_track_generate(args)
        elif args.track_action == "create":
            handle_track_create(args)
        elif args.track_action == "toggle":
            handle_track_toggle(args)
        else:
            parser.print_help()
    elif args.command == "plan":
        handle_plan_today(args)
    elif args.command == "log":
        handle_log(args)
    elif args.command == "status":
        handle_status(args)
    elif args.command == "sheet":
        if args.sheet_action == "generate" or not args.sheet_action:
            handle_sheet_generate(args)
        else:
            parser.print_help()
    elif args.command == "card":
        handle_card(args)
    elif args.command == "report":
        handle_report(args)
    else:
        parser.print_help()

