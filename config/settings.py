"""Configurações globais, leitura de variáveis de ambiente (.env) e rotina fixa."""

from datetime import date, time
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FixedCommitment(BaseModel):
    """Representa um compromisso fixo da rotina (aulas, trabalho, almoço, treino, sono)."""
    title: str
    start: str  # formato "HH:MM"
    end: str    # formato "HH:MM"
    days_of_week: List[int] = Field(
        default_factory=lambda: [0, 1, 2, 3, 4, 5, 6],
        description="Dias da semana onde 0=Segunda, 6=Domingo"
    )

    def start_time(self) -> time:
        h, m = map(int, self.start.split(":"))
        return time(hour=h, minute=m)

    def end_time(self) -> time:
        h, m = map(int, self.end.split(":"))
        return time(hour=h, minute=m)


class Settings(BaseSettings):
    """Configurações centrais do OrientAI com suporte a .env."""
    
    app_name: str = "OrientAI"
    app_version: str = "0.1.0"
    
    # AnkiConnect
    anki_url: str = "http://localhost:8765"
    anki_timeout_seconds: float = 3.0
    
    # Diretórios e caminhos
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = Path("data")
    
    # Metas e Prazos Unicamp
    unicamp_stage_1_date: date = date(2026, 10, 18)
    unicamp_stage_2_date: date = date(2026, 11, 29)
    target_course: str = "Engenharia de Computação / Ciência da Computação"
    
    # Google AI Studio (Gemini)
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"

    # Diretórios de Fontes e Worksheets
    sources_dir: Path = Path("tracks/sources")
    worksheets_dir: Path = Path("data/worksheets")

    # Parâmetros de Estudo
    daily_study_hours: float = 5.0
    pomodoro_work_minutes: int = 50
    pomodoro_break_minutes: int = 10
    anki_review_minutes: int = 15
    day_start_hour: int = 8    # Início da janela diária permitida de estudos (08:00)
    day_end_hour: int = 22     # Fim da janela diária de estudos (22:00)

    # Compromissos fixos padrão para não sobrepor (almoço, jantar, descanso/academia)
    routine_commitments: List[FixedCommitment] = Field(
        default_factory=lambda: [
            FixedCommitment(title="Almoço & Pausa", start="12:00", end="13:30"),
            FixedCommitment(title="Treino / Atividade Física", start="18:00", end="19:15"),
            FixedCommitment(title="Jantar", start="19:30", end="20:30"),
        ]
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def resolved_data_dir(self) -> Path:
        path = self.base_dir / self.data_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resolved_sources_dir(self) -> Path:
        path = self.base_dir / self.sources_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resolved_worksheets_dir(self) -> Path:
        path = self.base_dir / self.worksheets_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def state_file(self) -> Path:
        return self.resolved_data_dir / "state.json"

    @property
    def logs_dir(self) -> Path:
        path = self.resolved_data_dir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def anki_queue_file(self) -> Path:
        return self.resolved_data_dir / "anki_queue.json"

    @property
    def credentials_dir(self) -> Path:
        path = self.resolved_data_dir / "credentials"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def google_client_secret_file(self) -> Path:
        return self.credentials_dir / "client_secret.json"

    @property
    def google_token_file(self) -> Path:
        return self.credentials_dir / "token.json"


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Retorna instância singleton das configurações."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
