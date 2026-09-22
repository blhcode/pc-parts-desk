from __future__ import annotations

import time
from dataclasses import dataclass

from .config import settings


@dataclass
class PlaySession:
    active_save_id: str | None = None
    last_heartbeat: float = 0.0
    generating: bool = False

    def is_playing(self, save_id: str | None = None) -> bool:
        if not self.active_save_id:
            return False
        if save_id and save_id != self.active_save_id:
            return False
        return (time.time() - self.last_heartbeat) <= settings.heartbeat_timeout_sec

    def heartbeat(self, save_id: str) -> None:
        self.active_save_id = save_id
        self.last_heartbeat = time.time()

    def clear(self) -> None:
        self.active_save_id = None
        self.last_heartbeat = 0.0


session = PlaySession()
