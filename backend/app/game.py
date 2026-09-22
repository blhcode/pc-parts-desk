from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .models import JobHistoryEntry, Message, SaveGame, Thread


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reputation_band(reputation: int) -> dict[str, float | int]:
    r = max(0, min(100, reputation))
    if r < 20:
        return {"min_delay": 480, "max_delay": 1200, "max_open": 2, "sla_mult": 1.0}
    if r < 50:
        return {"min_delay": 300, "max_delay": 720, "max_open": 4, "sla_mult": 1.15}
    if r < 80:
        return {"min_delay": 180, "max_delay": 480, "max_open": 6, "sla_mult": 1.3}
    return {"min_delay": 120, "max_delay": 300, "max_open": 8, "sla_mult": 1.5}


def sla_thresholds(reputation: int) -> dict[str, float]:
    m = float(reputation_band(reputation)["sla_mult"])
    return {
        "warning": 8 * 60 * m,
        "impatient": 20 * 60 * m,
        "expired": 45 * 60 * m,
    }


def open_unanswered_count(save: SaveGame) -> int:
    return sum(1 for t in save.threads if t.status == "open" and t.folder == "inbox")


def response_time_score(play_seconds: float, reputation: int) -> float:
    th = sla_thresholds(reputation)
    if play_seconds <= th["warning"] * 0.5:
        return 5.0
    if play_seconds <= th["warning"]:
        return 4.0
    if play_seconds <= th["impatient"]:
        return 3.0
    if play_seconds <= th["expired"]:
        return 2.0
    return 1.0


def clamp_score(v: float) -> float:
    return max(1.0, min(5.0, float(v)))


def weighted_job_score(performance: float, response_time: float, service: float) -> float:
    return clamp_score(performance * 0.5 + response_time * 0.3 + service * 0.2)


def recompute_shop_rating(save: SaveGame) -> None:
    history = save.job_history[-30:]
    if not history:
        save.shop_rating = 3.0
        save.avg_performance = 3.0
        save.avg_response_time = 3.0
        save.avg_service = 3.0
        return
    save.shop_rating = round(sum(h.overall for h in history) / len(history), 2)
    save.avg_performance = round(sum(h.performance for h in history) / len(history), 2)
    save.avg_response_time = round(sum(h.response_time for h in history) / len(history), 2)
    save.avg_service = round(sum(h.service for h in history) / len(history), 2)


def check_game_over(save: SaveGame) -> str | None:
    closed = save.jobs_completed + save.jobs_failed
    if closed < 5:
        return None
    if save.bad_review_streak >= 3:
        return "three bad reviews in a row"
    recent = save.job_history[-10:]
    bad_recent = sum(1 for h in recent if h.bad)
    if len(recent) >= 10 and bad_recent >= 5:
        return "five bad reviews in the last ten jobs"
    return None


def apply_job_close(
    save: SaveGame,
    thread: Thread,
    *,
    performance: float,
    response_time: float,
    service: float,
    bad: bool,
    reason: str,
    failed: bool,
) -> str | None:
    overall = weighted_job_score(performance, response_time, service)
    entry = JobHistoryEntry(
        thread_id=thread.id,
        overall=overall,
        performance=clamp_score(performance),
        response_time=clamp_score(response_time),
        service=clamp_score(service),
        bad=bad or failed,
        reason=reason,
        closed_at=_now(),
    )
    save.job_history.append(entry)
    if failed:
        save.jobs_failed += 1
        save.reputation = max(0, save.reputation - 8)
        save.bad_review_streak += 1
    else:
        save.jobs_completed += 1
        if entry.bad:
            save.bad_review_streak += 1
            save.reputation = max(0, save.reputation - 4)
        else:
            save.bad_review_streak = 0
            gain = 3 + int(overall)
            save.reputation = min(100, save.reputation + gain)

    recompute_shop_rating(save)
    go = check_game_over(save)
    if go:
        save.status = "game_over"
        save.game_over_reason = go
    return go


def customer_from_ollama(data: dict[str, Any], shop_name: str) -> Thread:
    now = _now()
    tid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    name = data.get("from_name") or "Customer"
    email = data.get("from_email") or "customer@example.com"
    subject = data.get("subject") or f"PC build request for {shop_name}"
    body = data.get("body") or "Hi, I need a PC built."
    msg = Message(
        id=mid,
        role="customer",
        from_name=name,
        from_email=email,
        subject=subject,
        body=body,
        created_at=now,
    )
    return Thread(
        id=tid,
        folder="inbox",
        unread=True,
        status="open",
        customer_name=name,
        customer_email=email,
        subject=subject,
        preview=body[:120].replace("\n", " "),
        budget_aud=data.get("budget_aud"),
        use_case=str(data.get("use_case") or ""),
        must_haves=list(data.get("must_haves") or []),
        constraints=list(data.get("constraints") or []),
        messages=[msg],
        created_at=now,
        updated_at=now,
    )


def add_shop_reply(
    thread: Thread,
    *,
    shop_name: str,
    body: str,
    parts: list[dict[str, str]],
) -> Message:
    now = _now()
    from .models import Part

    msg = Message(
        id=str(uuid.uuid4()),
        role="shop",
        from_name=shop_name,
        from_email="builds@" + shop_name.lower().replace(" ", "") + ".local",
        subject=f"Re: {thread.subject}",
        body=body,
        created_at=now,
        parts=[Part(**p) if isinstance(p, dict) else p for p in parts],
    )
    thread.messages.append(msg)
    thread.updated_at = now
    thread.unread = False
    return msg


def add_customer_message(
    thread: Thread,
    *,
    subject: str,
    body: str,
    score_summary: dict[str, Any] | None = None,
) -> Message:
    now = _now()
    msg = Message(
        id=str(uuid.uuid4()),
        role="customer",
        from_name=thread.customer_name,
        from_email=thread.customer_email,
        subject=subject,
        body=body,
        created_at=now,
        score_summary=score_summary,
    )
    thread.messages.append(msg)
    thread.updated_at = now
    thread.unread = True
    thread.preview = body[:120].replace("\n", " ")
    return msg
