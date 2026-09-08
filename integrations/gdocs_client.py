"""Cliente de Integração com Google Docs API com Fallback Gracioso Local."""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from core.models import ExerciseList, ExerciseItem

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file"
]


class GoogleDocsClient:
    """Cliente para criação de listas de exercícios estilizadas no Google Docs."""

    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
        worksheets_dir: str = "data/worksheets"
    ):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.worksheets_dir = Path(worksheets_dir)
        self.worksheets_dir.mkdir(parents=True, exist_ok=True)
        self._docs_service = None
        self._drive_service = None

    def _slugify(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        return re.sub(r"[\s_-]+", "_", text)

    def _get_services(self):
        """Tenta autenticar com Google APIs. Retorna (docs_service, drive_service) ou (None, None)."""
        if self._docs_service and self._drive_service:
            return self._docs_service, self._drive_service

        if not os.path.exists(self.credentials_path) and not os.path.exists(self.token_path):
            return None, None

        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = None
            if os.path.exists(self.token_path):
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                elif os.path.exists(self.credentials_path):
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                else:
                    return None, None

                # Salva o token para as próximas execuções
                with open(self.token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())

            self._docs_service = build("docs", "v1", credentials=creds)
            self._drive_service = build("drive", "v3", credentials=creds)
            return self._docs_service, self._drive_service
        except Exception:
            return None, None

    def create_exercise_doc(self, title: str, exercise_list: ExerciseList) -> str:
        """Cria o documento no Google Docs ou aciona fallback gracioso em Markdown."""
        docs_service, drive_service = self._get_services()

        if docs_service is not None:
            try:
                return self._create_remote_gdoc(title, exercise_list, docs_service)
            except Exception:
                # Se falhar a chamada de rede ou permissão, aciona fallback
                pass

        return self._create_local_markdown(title, exercise_list)

    def _create_remote_gdoc(self, title: str, exercise_list: ExerciseList, docs_service) -> str:
        """Cria o Google Doc remotamente via API oficial."""
        body = {"title": title}
        doc = docs_service.documents().create(body=body).execute()
        doc_id = doc.get("documentId")

        # Constrói o texto do documento estruturado
        content_text = self._build_document_plain_text(title, exercise_list)

        requests = [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": content_text
                }
            }
        ]

        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": requests}
        ).execute()

        return f"https://docs.google.com/document/d/{doc_id}/edit"

    def _build_document_plain_text(self, title: str, exercise_list: ExerciseList) -> str:
        lines = []
        lines.append(f"🎯 ORIENTAI — LISTA DE EXERCÍCIOS DE ALTA PERFORMANCE\n")
        lines.append(f"{'='*60}\n")
        lines.append(f"Título: {title}\n")
        lines.append(f"Trilha: {exercise_list.track_id.upper()}\n")
        lines.append(f"Tópico: {exercise_list.topic_name}\n")
        lines.append(f"Escopo / Fontes: {exercise_list.source_scope}\n")
        lines.append(f"Meta de Acertos: {int(exercise_list.target_accuracy * 100)}% (Anti-Passividade)\n")
        lines.append(f"Data de Geração: {exercise_list.created_at[:10]}\n")
        lines.append(f"{'='*60}\n\n")

        for lvl in [1, 2, 3]:
            lvl_items = [e for e in exercise_list.exercises if e.level == lvl]
            if not lvl_items:
                continue
            lines.append(f"\n{'-'*50}\n")
            lines.append(f"📌 {lvl_items[0].level_name.upper()}\n")
            lines.append(f"{'-'*50}\n\n")

            for i, ex in enumerate(lvl_items, 1):
                lines.append(f"[QUESTÃO {ex.id.upper()}] ({ex.source or 'OrientAI'})\n")
                lines.append(f"{ex.statement}\n\n")
                if ex.options:
                    for opt in ex.options:
                        lines.append(f"  {opt}\n")
                    lines.append("\n")
                lines.append(f"┌────────────────────────────────────────────────────────┐\n")
                lines.append(f"│ ESPAÇO PARA DEDUÇÃO / RESOLUÇÃO / RASCUNHO             │\n")
                lines.append(f"│                                                        │\n")
                lines.append(f"│                                                        │\n")
                lines.append(f"│ Resposta Final do Estudante: [                        ] │\n")
                lines.append(f"└────────────────────────────────────────────────────────┘\n\n")

        lines.append(f"\n{'='*60}\n")
        lines.append(f"🔑 GABARITO OFICIAL & RESOLUÇÃO RESUMIDA\n")
        lines.append(f"{'='*60}\n\n")
        for ex in exercise_list.exercises:
            lines.append(f"• {ex.id.upper()} ({ex.level_name}): {ex.answer_key}\n")
            if ex.explanation:
                lines.append(f"  Justificativa: {ex.explanation}\n")
        lines.append("\n")

        return "".join(lines)

    def _create_local_markdown(self, title: str, exercise_list: ExerciseList) -> str:
        """Gera arquivo Markdown local com diagramação completa para impressão ou estudo offline."""
        timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
        topic_slug = self._slugify(exercise_list.topic_name)
        track_slug = self._slugify(exercise_list.track_id)
        filename = f"worksheet_{track_slug}_{topic_slug}_{timestamp_slug}.md"
        file_path = self.worksheets_dir / filename

        md_lines = [
            f"# 🎯 OrientAI — Lista de Exercícios Tangíveis",
            f"",
            f"> **Trilha:** `{exercise_list.track_id}` | **Tópico:** **{exercise_list.topic_name}** | **Meta:** `{int(exercise_list.target_accuracy * 100)}%`",
            f"> **Escopo:** *{exercise_list.source_scope}* | **Gerado em:** `{exercise_list.created_at[:16].replace('T', ' ')}`",
            f"",
            f"---",
            f"",
            f"### 📋 Instruções de Execução (Regra Anti-Passividade)",
            f"1. **Tempo de Resolução Focada:** Dedique blocos de 50 minutos sem interrupções.",
            f"2. **Obrigatoriedade de Registro:** Preencha o rascunho de cada questão e aponte a resposta final.",
            f"3. **Maestria do Nó:** Para desbloquear o próximo nó do grafo, atinja no mínimo **{int(exercise_list.target_accuracy * 100)}% de acertos**.",
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
                    f"│ [ ] Resposta Final: _________________________________________________________ │",
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

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return str(file_path)
