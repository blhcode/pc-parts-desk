from __future__ import annotations

import asyncio
import logging
import random

from . import game, ollama_client, store
from .session import session

logger = logging.getLogger(__name__)

TICK_SEC = 1.0


async def _maybe_generate_inbound() -> None:
    if not session.is_playing() or session.generating:
        return
    save_id = session.active_save_id
    if not save_id:
        return
    try:
        save = store.get_save(save_id)
    except FileNotFoundError:
        return
    if save.status != "active":
        return

    band = game.reputation_band(save.reputation)
    if game.open_unanswered_count(save) >= int(band["max_open"]):
        return

    if save.inbound_play_seconds_until_next is None:
        if not save.first_mail_sent:
            save.inbound_play_seconds_until_next = random.uniform(45, 90)
        else:
            save.inbound_play_seconds_until_next = random.uniform(
                float(band["min_delay"]), float(band["max_delay"])
            )
        store.save_game(save)
        return

    # Countdown is decremented in tick; when <= 0 generate
    if save.inbound_play_seconds_until_next > 0:
        return

    session.generating = True
    try:
        recent = [
            {
                "from_name": t.customer_name,
                "budget_aud": t.budget_aud,
                "use_case": t.use_case,
                "subject": t.subject,
            }
            for t in save.threads[:12]
        ]
        data = await ollama_client.generate_customer(
            save.shop_name, save.reputation, recent=recent
        )
        # reload in case of concurrent writes
        save = store.get_save(save_id)
        if save.status != "active" or not session.is_playing(save_id):
            return
        thread = game.customer_from_ollama(data, save.shop_name)
        save.threads.insert(0, thread)
        save.first_mail_sent = True
        band = game.reputation_band(save.reputation)
        save.inbound_play_seconds_until_next = random.uniform(
            float(band["min_delay"]), float(band["max_delay"])
        )
        store.save_game(save)
        logger.info(
            "New inbound for %s: %s ($%s · %s)",
            save.shop_name,
            thread.subject,
            thread.budget_aud,
            thread.use_case,
        )
    except Exception:
        logger.exception("Failed to generate customer email")
        try:
            save = store.get_save(save_id)
            save.inbound_play_seconds_until_next = 60.0
            store.save_game(save)
        except Exception:
            pass
    finally:
        session.generating = False


def _advance_sla(save_id: str, dt: float) -> None:
    save = store.get_save(save_id)
    if save.status != "active":
        return
    th = game.sla_thresholds(save.reputation)
    changed = False

    for thread in save.threads:
        if thread.status != "open":
            continue
        # Ball in customer's court — don't punish the shop for waiting on a reply
        if getattr(thread, "awaiting_customer_reply", False):
            continue
        thread.play_seconds_open += dt
        changed = True
        sec = thread.play_seconds_open

        if sec >= th["expired"] and thread.sla_stage != "expired":
            thread.sla_stage = "expired"
            thread.status = "cancelled"
            thread.folder = "inbox"
            body = (
                f"Hi {save.shop_name},\n\n"
                "I've waited long enough and found another builder. "
                "Please cancel my request.\n\n"
                f"— {thread.customer_name}"
            )
            game.add_customer_message(
                thread,
                subject=f"Cancelling: {thread.subject}",
                body=body,
            )
            go = game.apply_job_close(
                save,
                thread,
                performance=1.0,
                response_time=1.0,
                service=1.0,
                bad=True,
                reason="SLA expired",
                failed=True,
            )
            thread.job_result = {"overall": 1.0, "reason": "SLA expired", "game_over": go}
            continue

        if sec >= th["impatient"] and thread.sla_stage not in ("impatient", "expired"):
            thread.sla_stage = "impatient"
            if not thread.impatient_penalty_applied:
                thread.impatient_penalty_applied = True
                nudge = (
                    f"Hi,\n\nJust checking in — any update on my PC build? "
                    f"Still hoping to hear back soon.\n\n— {thread.customer_name}"
                )
                game.add_customer_message(
                    thread,
                    subject=f"Following up: {thread.subject}",
                    body=nudge,
                )
        elif sec >= th["warning"] and thread.sla_stage == "ok":
            thread.sla_stage = "warning"

    if save.inbound_play_seconds_until_next is not None:
        save.inbound_play_seconds_until_next = max(
            0.0, save.inbound_play_seconds_until_next - dt
        )
        changed = True

    if changed:
        store.save_game(save)


async def game_loop(stop: asyncio.Event) -> None:
    logger.info("Game loop started")
    while not stop.is_set():
        try:
            if session.is_playing() and session.active_save_id:
                _advance_sla(session.active_save_id, TICK_SEC)
                await _maybe_generate_inbound()
        except Exception:
            logger.exception("Game loop tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=TICK_SEC)
        except asyncio.TimeoutError:
            pass
    logger.info("Game loop stopped")
