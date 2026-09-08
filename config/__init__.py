"""Módulo de configuração do OrientAI."""

from config.settings import Settings, get_settings, FixedCommitment
from config.subjects import Subject, SubjectType, SubjectConfig, DEFAULT_SUBJECTS

__all__ = [
    "Settings",
    "get_settings",
    "FixedCommitment",
    "Subject",
    "SubjectType",
    "SubjectConfig",
    "DEFAULT_SUBJECTS",
]
