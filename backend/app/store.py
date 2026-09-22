from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import SaveGame, SaveSummary

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "saves"
INDEX_PATH = DATA_DIR / "index.json"
_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        INDEX_PATH.write_text(json.dumps({"saves": [], "active_save_id": None}, indent=2))


def _read_index() -> dict:
    ensure_dirs()
    return json.loads(INDEX_PATH.read_text())


def _write_index(data: dict) -> None:
    ensure_dirs()
    INDEX_PATH.write_text(json.dumps(data, indent=2))


def _save_path(save_id: str) -> Path:
    return DATA_DIR / f"{save_id}.json"


def list_saves() -> list[SaveSummary]:
    with _lock:
        idx = _read_index()
        out: list[SaveSummary] = []
        for sid in idx.get("saves", []):
            path = _save_path(sid)
            if not path.exists():
                continue
            raw = json.loads(path.read_text())
            out.append(
                SaveSummary(
                    id=raw["id"],
                    shop_name=raw["shop_name"],
                    created_at=raw["created_at"],
                    last_played=raw["last_played"],
                    status=raw.get("status", "active"),
                    shop_rating=raw.get("shop_rating", 3.0),
                    jobs_completed=raw.get("jobs_completed", 0),
                    reputation=raw.get("reputation", 0),
                    game_over_reason=raw.get("game_over_reason", ""),
                )
            )
        out.sort(key=lambda s: s.last_played, reverse=True)
        return out


def create_save(shop_name: str) -> SaveGame:
    with _lock:
        idx = _read_index()
        if len(idx.get("saves", [])) >= 5:
            raise ValueError("Maximum of 5 save slots reached")
        name = shop_name.strip()
        if not name:
            raise ValueError("Shop name is required")
        now = _now()
        save = SaveGame(
            id=str(uuid.uuid4()),
            shop_name=name,
            created_at=now,
            last_played=now,
        )
        path = _save_path(save.id)
        path.write_text(save.model_dump_json(indent=2))
        idx.setdefault("saves", []).append(save.id)
        _write_index(idx)
        return save


def load_save(save_id: str) -> SaveGame:
    with _lock:
        path = _save_path(save_id)
        if not path.exists():
            raise FileNotFoundError(f"Save not found: {save_id}")
        save = SaveGame.model_validate_json(path.read_text())
        save.last_played = _now()
        path.write_text(save.model_dump_json(indent=2))
        idx = _read_index()
        idx["active_save_id"] = save_id
        _write_index(idx)
        return save


def get_active_save_id() -> str | None:
    with _lock:
        return _read_index().get("active_save_id")


def get_save(save_id: str) -> SaveGame:
    with _lock:
        path = _save_path(save_id)
        if not path.exists():
            raise FileNotFoundError(f"Save not found: {save_id}")
        return SaveGame.model_validate_json(path.read_text())


def save_game(save: SaveGame) -> None:
    with _lock:
        save.last_played = _now()
        _save_path(save.id).write_text(save.model_dump_json(indent=2))


def delete_save(save_id: str) -> None:
    with _lock:
        idx = _read_index()
        if save_id in idx.get("saves", []):
            idx["saves"] = [s for s in idx["saves"] if s != save_id]
        if idx.get("active_save_id") == save_id:
            idx["active_save_id"] = None
        _write_index(idx)
        path = _save_path(save_id)
        if path.exists():
            path.unlink()


def unload_active() -> None:
    with _lock:
        idx = _read_index()
        idx["active_save_id"] = None
        _write_index(idx)
