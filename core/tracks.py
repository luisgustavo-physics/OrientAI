"""Gerenciador de Trilhas de Estudo (Study Tracks) do OrientAI."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import Settings, get_settings
from core.models import StudyTrack, SubjectConfig


class TrackManager:
    """Carrega, valida, persiste e consulta trilhas de estudo modulares."""

    def __init__(self, settings: Optional[Settings] = None, tracks_dir: Optional[Path] = None):
        self.settings = settings or get_settings()
        self.tracks_dir = tracks_dir or (self.settings.base_dir / "tracks")
        self.tracks_dir.mkdir(parents=True, exist_ok=True)
        self._tracks_cache: Optional[Dict[str, StudyTrack]] = None

    def load_all_tracks(self, refresh: bool = False) -> Dict[str, StudyTrack]:
        """Carrega todas as trilhas disponíveis no diretório tracks/."""
        if self._tracks_cache is not None and not refresh:
            return self._tracks_cache

        tracks: Dict[str, StudyTrack] = {}
        if not self.tracks_dir.exists():
            self._tracks_cache = tracks
            return tracks

        for path in sorted(self.tracks_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                track = StudyTrack.model_validate(data)
                tracks[track.id] = track
            except Exception as e:
                # Se falhar o carregamento de uma trilha individual, registra e prossegue
                print(f"Aviso: Falha ao carregar trilha {path.name}: {e}")

        self._tracks_cache = tracks
        return tracks

    def get_track(self, track_id: str) -> Optional[StudyTrack]:
        """Retorna uma trilha específica pelo ID."""
        tracks = self.load_all_tracks()
        return tracks.get(track_id)

    def get_active_tracks(self) -> List[StudyTrack]:
        """Retorna todas as trilhas marcadas como ativas."""
        tracks = self.load_all_tracks()
        return [t for t in tracks.values() if t.is_active]

    def save_track(self, track: StudyTrack) -> Path:
        """Salva ou atualiza a definição de uma trilha em disco."""
        file_path = self.tracks_dir / f"{track.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(track.model_dump(), f, indent=2, ensure_ascii=False)
        
        # Invalida cache
        if self._tracks_cache is not None:
            self._tracks_cache[track.id] = track
        return file_path

    def create_track(self, track: StudyTrack) -> Path:
        """Registra uma nova trilha de estudo."""
        return self.save_track(track)

    def toggle_track(self, track_id: str, is_active: Optional[bool] = None) -> bool:
        """Ativa ou desativa uma trilha."""
        track = self.get_track(track_id)
        if not track:
            return False

        if is_active is None:
            track.is_active = not track.is_active
        else:
            track.is_active = is_active

        self.save_track(track)
        return True

    def find_subject_track(self, subject_query: str) -> Optional[Tuple[StudyTrack, SubjectConfig]]:
        """Busca em qual trilha uma determinada matéria está registrada."""
        tracks = self.load_all_tracks()
        query = subject_query.lower().strip()

        # Primeiro verifica em trilhas ativas
        active = [t for t in tracks.values() if t.is_active]
        inactive = [t for t in tracks.values() if not t.is_active]

        for track in active + inactive:
            if query in track.subjects:
                return track, track.subjects[query]
            for s in track.subjects.values():
                if s.name.lower() == query or s.id.lower() == query:
                    return track, s
        return None
