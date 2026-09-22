from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import game, ollama_client, pcpp, store
from .config import settings
from .models import CreateSaveRequest, PcppResolveRequest, ReplyRequest
from .scheduler import game_loop
from .session import session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_stop: asyncio.Event | None = None
_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _stop, _task
    store.ensure_dirs()
    _stop = asyncio.Event()
    _task = asyncio.create_task(game_loop(_stop))
    yield
    _stop.set()
    if _task:
        await _task


app = FastAPI(title="PC Parts Desk", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_active_save():
    sid = session.active_save_id or store.get_active_save_id()
    if not sid:
        raise HTTPException(400, "No save loaded")
    try:
        return store.get_save(sid)
    except FileNotFoundError:
        raise HTTPException(404, "Save not found")


@app.get("/api/health")
def health():
    return {"ok": True, "model": settings.ollama_model}


@app.get("/api/saves")
def list_saves():
    return {"saves": [s.model_dump() for s in store.list_saves()]}


@app.post("/api/saves")
def create_save(body: CreateSaveRequest):
    try:
        save = store.create_save(body.shop_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return save.model_dump()


@app.post("/api/saves/{save_id}/load")
def load_save(save_id: str):
    try:
        save = store.load_save(save_id)
    except FileNotFoundError:
        raise HTTPException(404, "Save not found")
    session.active_save_id = save_id
    # Don't start play-time until heartbeat
    session.last_heartbeat = 0.0
    return save.model_dump()


@app.delete("/api/saves/{save_id}")
def delete_save(save_id: str):
    store.delete_save(save_id)
    if session.active_save_id == save_id:
        session.clear()
    return {"ok": True}


@app.post("/api/unload")
def unload():
    session.clear()
    store.unload_active()
    return {"ok": True}


@app.post("/api/heartbeat")
def heartbeat():
    sid = session.active_save_id or store.get_active_save_id()
    if not sid:
        raise HTTPException(400, "No save loaded")
    save = store.get_save(sid)
    if save.status == "game_over":
        return {"ok": True, "playing": False, "game_over": True, "reason": save.game_over_reason}
    session.heartbeat(sid)
    return {
        "ok": True,
        "playing": True,
        "inbound_eta": save.inbound_play_seconds_until_next,
        "open_jobs": game.open_unanswered_count(save),
    }


@app.get("/api/shop")
def shop():
    save = _require_active_save()
    return {
        "id": save.id,
        "shop_name": save.shop_name,
        "status": save.status,
        "game_over_reason": save.game_over_reason,
        "shop_rating": save.shop_rating,
        "avg_performance": save.avg_performance,
        "avg_response_time": save.avg_response_time,
        "avg_service": save.avg_service,
        "jobs_completed": save.jobs_completed,
        "jobs_failed": save.jobs_failed,
        "reputation": save.reputation,
        "bad_review_streak": save.bad_review_streak,
        "playing": session.is_playing(save.id),
    }


@app.get("/api/inbox")
def inbox(folder: str = "inbox"):
    save = _require_active_save()
    threads = [t for t in save.threads if t.folder == folder or (folder == "inbox" and t.folder == "inbox")]
    if folder == "sent":
        threads = [t for t in save.threads if any(m.role == "shop" for m in t.messages)]
    elif folder == "archive":
        threads = [t for t in save.threads if t.folder == "archive"]
    else:
        threads = [t for t in save.threads if t.folder == "inbox"]

    def summary(t):
        return {
            "id": t.id,
            "unread": t.unread,
            "status": t.status,
            "sla_stage": t.sla_stage,
            "play_seconds_open": t.play_seconds_open,
            "from_name": t.customer_name,
            "from_email": t.customer_email,
            "subject": t.subject,
            "preview": t.preview,
            "updated_at": t.updated_at,
            "created_at": t.created_at,
        }

    threads_sorted = sorted(threads, key=lambda t: t.updated_at, reverse=True)
    return {
        "folder": folder,
        "threads": [summary(t) for t in threads_sorted],
        "shop": {
            "shop_name": save.shop_name,
            "shop_rating": save.shop_rating,
            "jobs_completed": save.jobs_completed,
            "status": save.status,
            "game_over_reason": save.game_over_reason,
            "reputation": save.reputation,
            "avg_performance": save.avg_performance,
            "avg_response_time": save.avg_response_time,
            "avg_service": save.avg_service,
        },
    }


@app.get("/api/threads/{thread_id}")
def get_thread(thread_id: str):
    save = _require_active_save()
    thread = next((t for t in save.threads if t.id == thread_id), None)
    if not thread:
        raise HTTPException(404, "Thread not found")
    if thread.unread:
        thread.unread = False
        store.save_game(save)
    return thread.model_dump()


@app.post("/api/threads/{thread_id}/archive")
def archive_thread(thread_id: str):
    save = _require_active_save()
    if save.status == "game_over":
        raise HTTPException(400, "Shop is closed")
    thread = next((t for t in save.threads if t.id == thread_id), None)
    if not thread:
        raise HTTPException(404, "Thread not found")
    thread.folder = "archive"
    store.save_game(save)
    return {"ok": True}


@app.post("/api/pcpp/resolve")
async def resolve_pcpp(body: PcppResolveRequest):
    try:
        result = await pcpp.resolve_list(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, str(e))
    return result


@app.post("/api/threads/{thread_id}/reply")
async def reply_thread(thread_id: str, body: ReplyRequest):
    save = _require_active_save()
    if save.status == "game_over":
        raise HTTPException(400, "Shop is closed — game over")

    thread = next((t for t in save.threads if t.id == thread_id), None)
    if not thread:
        raise HTTPException(404, "Thread not found")
    if thread.status != "open":
        raise HTTPException(400, "This request is no longer open")

    has_parts = bool((body.pcpp_url and body.pcpp_url.strip()) or (body.parts_text and body.parts_text.strip()))
    mode = body.mode
    if mode is None:
        mode = "proposal" if has_parts else "message"

    notes = (body.notes or "").strip()

    # --- Clarifying Q&A: stay open, customer answers ---
    if mode == "message":
        if not notes:
            raise HTTPException(400, "Write a message to the customer (questions, options, etc.)")
        if has_parts:
            raise HTTPException(
                400,
                "This looks like a parts proposal — use Send parts proposal, or clear the list fields to only ask a question.",
            )

        game.add_shop_reply(thread, shop_name=save.shop_name, body=notes, parts=[])
        thread.awaiting_customer_reply = True

        brief = {
            "budget_aud": thread.budget_aud,
            "use_case": thread.use_case,
            "must_haves": thread.must_haves,
            "constraints": thread.constraints,
            "original_body": thread.messages[0].body if thread.messages else "",
        }
        transcript = [
            {"role": m.role, "from": m.from_name, "body": m.body[:2000]}
            for m in thread.messages[-12:]
        ]
        try:
            reply = await ollama_client.customer_reply_to_shop(
                shop_name=save.shop_name,
                customer_name=thread.customer_name,
                brief=brief,
                transcript=transcript,
                shop_message=notes,
            )
        except Exception as e:
            logger.exception("Customer Q&A reply failed")
            thread.awaiting_customer_reply = False
            store.save_game(save)
            raise HTTPException(502, f"Ollama customer reply failed: {e}")

        game.add_customer_message(
            thread,
            subject=str(reply.get("subject") or f"Re: {thread.subject}"),
            body=str(reply.get("body") or "Happy to answer — what else do you need?"),
        )
        thread.awaiting_customer_reply = False
        thread.status = "open"
        store.save_game(save)
        return {
            "thread": thread.model_dump(),
            "shop": {
                "shop_name": save.shop_name,
                "shop_rating": save.shop_rating,
                "avg_performance": save.avg_performance,
                "avg_response_time": save.avg_response_time,
                "avg_service": save.avg_service,
                "jobs_completed": save.jobs_completed,
                "status": save.status,
                "game_over_reason": save.game_over_reason,
                "reputation": save.reputation,
            },
            "game_over": False,
            "kind": "message",
        }

    # --- Final parts proposal ---
    parts: list[dict[str, Any]] = []
    total_aud: float | None = None
    if body.pcpp_url and body.pcpp_url.strip():
        try:
            resolved = await pcpp.resolve_list(body.pcpp_url.strip())
            parts = resolved["parts"]
            total_aud = resolved.get("total_aud")
        except Exception as e:
            if body.parts_text and body.parts_text.strip():
                parsed, total_aud = pcpp.parse_parts_text(body.parts_text)
                parts = [p.model_dump() for p in parsed]
            else:
                raise HTTPException(
                    502,
                    f"Could not read PCPartPicker list ({e}). Paste the parts list text as a fallback.",
                )
    elif body.parts_text and body.parts_text.strip():
        try:
            parsed, total_aud = pcpp.parse_parts_text(body.parts_text)
            parts = [p.model_dump() for p in parsed]
        except ValueError as e:
            raise HTTPException(400, str(e))
    else:
        raise HTTPException(400, "Provide a PCPartPicker URL or pasted parts text for the final proposal")

    if body.parts_text and body.parts_text.strip() and body.pcpp_url:
        try:
            pasted, pasted_total = pcpp.parse_parts_text(body.parts_text)
            if len(pasted) >= len(parts) and all(p.name for p in pasted):
                if sum(1 for p in pasted if p.price) >= sum(1 for p in parts if p.get("price")):
                    parts = [p.model_dump() for p in pasted]
                    if pasted_total is not None:
                        total_aud = pasted_total
        except ValueError:
            pass

    total_aud = pcpp.parts_total_aud(parts, total_aud)
    facts = pcpp.budget_facts(thread.budget_aud, total_aud)

    reply_body = notes or "Here's the parts list I put together for you."
    if body.pcpp_url:
        reply_body += f"\n\nPCPartPicker: {body.pcpp_url.strip()}"
    reply_body += "\n\nParts:\n" + "\n".join(
        f"- {p.get('type', '')}: {p.get('name', '')} {p.get('price', '')}".strip() for p in parts
    )
    if total_aud is not None:
        reply_body += f"\n\nList total (parsed): ${total_aud:.2f} AUD"
        if thread.budget_aud is not None:
            reply_body += f" · Customer budget: ${float(thread.budget_aud):.2f} AUD · {facts['status']}"

    game.add_shop_reply(thread, shop_name=save.shop_name, body=reply_body, parts=parts)
    thread.awaiting_customer_reply = False
    play_seconds = thread.play_seconds_open
    rt_score = game.response_time_score(play_seconds, save.reputation)
    if thread.impatient_penalty_applied:
        rt_score = max(1.0, rt_score - 0.5)

    brief = {
        "budget_aud": thread.budget_aud,
        "use_case": thread.use_case,
        "must_haves": thread.must_haves,
        "constraints": thread.constraints,
        "original_body": thread.messages[0].body if thread.messages else "",
        "thread_messages": [
            {"role": m.role, "body": m.body[:1500]} for m in thread.messages[:-1][-10:]
        ],
    }

    try:
        review = await ollama_client.review_build(
            shop_name=save.shop_name,
            customer_name=thread.customer_name,
            brief=brief,
            parts=parts,
            notes=notes,
            play_seconds=play_seconds,
            budget_facts=facts,
        )
    except Exception as e:
        logger.exception("Review failed")
        raise HTTPException(502, f"Ollama review failed: {e}")

    perf = game.clamp_score(float(review.get("performance_score", 3)))
    service = game.clamp_score(float(review.get("service_score", 3)))
    if thread.impatient_penalty_applied:
        service = max(1.0, service - 0.5)

    overall = game.weighted_job_score(perf, rt_score, service)
    bad = overall < 2.5

    score_summary = {
        "overall": round(overall, 2),
        "performance": round(perf, 2),
        "response_time": round(rt_score, 2),
        "service": round(service, 2),
        "pros": review.get("pros") or [],
        "cons": review.get("cons") or [],
        "suggested_swaps": review.get("suggested_swaps") or [],
    }

    game.add_customer_message(
        thread,
        subject=str(review.get("subject") or f"Re: {thread.subject}"),
        body=str(review.get("body") or "Thanks for the build."),
        score_summary=score_summary,
    )
    thread.status = "completed"
    thread.sla_stage = "ok"
    go = game.apply_job_close(
        save,
        thread,
        performance=perf,
        response_time=rt_score,
        service=service,
        bad=bad,
        reason="completed",
        failed=False,
    )
    thread.job_result = {**score_summary, "game_over": go, "game_over_reason": save.game_over_reason}
    store.save_game(save)

    return {
        "thread": thread.model_dump(),
        "shop": {
            "shop_name": save.shop_name,
            "shop_rating": save.shop_rating,
            "avg_performance": save.avg_performance,
            "avg_response_time": save.avg_response_time,
            "avg_service": save.avg_service,
            "jobs_completed": save.jobs_completed,
            "status": save.status,
            "game_over_reason": save.game_over_reason,
            "reputation": save.reputation,
        },
        "game_over": go is not None,
        "kind": "proposal",
    }
