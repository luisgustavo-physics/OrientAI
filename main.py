#!/usr/bin/env python3
"""OrientAI - Agente Geral de Estudos de Alta Performance baseado em Trilhas (Study Tracks).
"""

import sys
from pathlib import Path

# Adiciona o diretório raiz ao path para execução sem necessidade de pip install -e .
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config.settings import get_settings
from core.state import StateManager
from cli.interface import run_cli


def initialize_environment() -> None:
    """Garante que as pastas de dados e o estado inicial estejam prontos."""
    settings = get_settings()
    settings.resolved_data_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Inicializa estado padrão se não existir
    state_manager = StateManager(settings)
    state_manager.load_state()


def main() -> None:
    """Função principal."""
    initialize_environment()
    run_cli()


if __name__ == "__main__":
    main()
