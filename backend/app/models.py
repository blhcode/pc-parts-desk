from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class Part(BaseModel):
    type: str = ""
    name: str = ""
    price: str = ""
    url: str = ""


class Message(BaseModel):
    id: str
    role: Literal["customer", "shop", "system"]
    from_name: str = ""
    from_email: str = ""
    subject: str = ""
    body: str = ""
    created_at: str
    parts: list[Part] = Field(default_factory=list)
    score_summary: dict[str, Any] | None = None


class Thread(BaseModel):
    id: str
    folder: Literal["inbox", "sent", "archive"] = "inbox"
    unread: bool = True
    status: Literal["open", "awaiting_review", "completed", "cancelled"] = "open"
    sla_stage: Literal["ok", "warning", "impatient", "expired"] = "ok"
    play_seconds_open: float = 0.0
    customer_name: str = ""
    customer_email: str = ""
    subject: str = ""
    preview: str = ""
    budget_aud: float | None = None
    use_case: str = ""
    must_haves: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    created_at: str
    updated_at: str
    impatient_penalty_applied: bool = False
    awaiting_customer_reply: bool = False
    job_result: dict[str, Any] | None = None


class JobHistoryEntry(BaseModel):
    thread_id: str
    overall: float
    performance: float
    response_time: float
    service: float
    bad: bool
    reason: str = ""
    closed_at: str


class SaveGame(BaseModel):
    id: str
    shop_name: str
    created_at: str
    last_played: str
    status: Literal["active", "game_over"] = "active"
    game_over_reason: str = ""
    shop_rating: float = 3.0
    avg_performance: float = 3.0
    avg_response_time: float = 3.0
    avg_service: float = 3.0
    jobs_completed: int = 0
    jobs_failed: int = 0
    bad_review_streak: int = 0
    reputation: int = 0
    threads: list[Thread] = Field(default_factory=list)
    job_history: list[JobHistoryEntry] = Field(default_factory=list)
    inbound_play_seconds_until_next: float | None = None
    first_mail_sent: bool = False


class SaveSummary(BaseModel):
    id: str
    shop_name: str
    created_at: str
    last_played: str
    status: str
    shop_rating: float
    jobs_completed: int
    reputation: int
    game_over_reason: str = ""


class CreateSaveRequest(BaseModel):
    shop_name: str = Field(min_length=1, max_length=64)


class ReplyRequest(BaseModel):
    """message-only = Q&A (thread stays open). parts = final proposal (closes with review)."""
    pcpp_url: str | None = None
    parts_text: str | None = None
    notes: str = ""
    mode: Literal["message", "proposal"] | None = None


class PcppResolveRequest(BaseModel):
    url: str
