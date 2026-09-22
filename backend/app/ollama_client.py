from __future__ import annotations

import json
import logging
import random
import re
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)

CUSTOMER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "from_name": {"type": "string"},
        "from_email": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "budget_aud": {"type": "number"},
        "use_case": {"type": "string"},
        "must_haves": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "from_name",
        "from_email",
        "subject",
        "body",
        "budget_aud",
        "use_case",
        "must_haves",
        "constraints",
    ],
}

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "performance_score": {"type": "number"},
        "service_score": {"type": "number"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "pros": {"type": "array", "items": {"type": "string"}},
        "cons": {"type": "array", "items": {"type": "string"}},
        "suggested_swaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "performance_score",
        "service_score",
        "subject",
        "body",
        "pros",
        "cons",
        "suggested_swaps",
    ],
}


async def chat_json(
    system: str,
    user: str,
    schema: dict[str, Any],
    *,
    temperature: float = 0.8,
) -> dict[str, Any]:
    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "format": schema,
        "options": {"temperature": temperature},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(settings.ollama_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    content = data.get("message", {}).get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            return json.loads(match.group(0))
        raise


async def generate_customer(
    shop_name: str,
    reputation: int,
    recent: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Invent a customer. Budget/archetype are chosen in code so Ollama cannot spam $800 Minecraft emails."""
    recent = recent or []

    # Reputation nudges the band, but we still sample widely so early game isn't identical.
    if reputation < 20:
        budget_choices = [450, 550, 650, 750, 900, 1100, 1300, 1500]
    elif reputation < 50:
        budget_choices = [700, 900, 1100, 1400, 1600, 1800, 2000, 2500]
    elif reputation < 80:
        budget_choices = [1200, 1500, 1800, 2200, 2800, 3200, 4000]
    else:
        budget_choices = [2000, 2500, 3000, 4000, 5000, 6500, 8000]

    recent_budgets = {int(r.get("budget_aud") or 0) for r in recent}
    pool = [b for b in budget_choices if b not in recent_budgets] or budget_choices
    budget = random.choice(pool)

    archetypes = [
        ("office / study machine", "web, docs, Zoom, light photo edits — not a gaming PC"),
        ("1080p esports", "Valorant/CS/League at high refresh; keep it efficient"),
        ("1080p mainstream gaming", "AAA titles at high settings, 60–100+ fps"),
        ("1440p gaming", "modern AAA at 1440p; budget must actually support this"),
        ("4K / ultra gaming", "only if budget is high enough; otherwise refuse the premise"),
        ("content creation", "video editing / streaming / Blender — CPU/RAM/storage heavy"),
        ("HTPC / living room", "quiet, small-ish, media + light gaming"),
        ("LAN party / portable LAN box", "compact, tough, easy to carry"),
        ("sim racing / flight sim", "CPU+GPU balanced, good cooling"),
        ("kids / family shared PC", "reliable, no RGB obsession, easy to service"),
        ("homelab / NAS-ish desktop", "many drives, quiet, not a 4090 flex build"),
        ("photo / music production", "fast storage, lots of RAM, quiet"),
        ("upgrade advice from old parts", "customer already owns some parts; partial list"),
        ("used / marketplace hunter", "open to second-hand GPU/CPU to stretch budget"),
        ("RGB showcase", "looks matter as much as frames"),
        ("SFF mini-ITX challenge", "small case, airflow/PSU constraints"),
    ]
    recent_uses = {(r.get("use_case") or "").lower() for r in recent}
    arch_pool = [a for a in archetypes if a[0] not in recent_uses] or archetypes
    use_case, use_hint = random.choice(arch_pool)

    tones = [
        "polite and a bit unsure",
        "blunt and impatient",
        "friendly tradie vibe",
        "techy but wrong about prices",
        "parent buying for a kid",
        "uni student counting every dollar",
        "retiree wanting something simple",
        "streamer obsessing over RGB and mics",
    ]
    tone = random.choice(tones)

    constraints_pool = [
        ["quiet for a bedroom"],
        ["no RGB"],
        ["RGB is fine"],
        ["ITX / small case"],
        ["must reuse an existing case"],
        ["Wi‑Fi needed"],
        ["white aesthetic"],
        ["max power draw concern / apartment"],
        ["prefer AMD"],
        ["prefer Intel/NVIDIA"],
        ["open to used parts"],
        ["new parts only / warranty"],
        ["needs good webcam/mic guidance too"],
        ["shipping to regional Australia"],
    ]
    constraints = random.sample(constraints_pool, k=random.randint(1, 3))
    flat_constraints = [c for group in constraints for c in group]

    avoid_lines = []
    for r in recent[-8:]:
        avoid_lines.append(
            f"- {r.get('from_name')}: budget ${r.get('budget_aud')}, use_case={r.get('use_case')}, "
            f"subject={r.get('subject')}"
        )
    avoid_block = "\n".join(avoid_lines) if avoid_lines else "(none yet)"

    system = (
        "You invent realistic customers emailing a small Australian PC building shop. "
        "Write natural email prose in Australian English. "
        "You MUST follow the assigned budget_aud and use_case exactly — do not change them. "
        "Do not invent a different budget. Do not default to $800. "
        "Names and emails must be unique and not reuse recent customers. "
        "Respond ONLY with JSON matching the schema."
    )
    user = (
        f"Create one new customer email to the shop \"{shop_name}\".\n"
        f"REQUIRED budget_aud: {budget} (AUD). Put this exact number in budget_aud.\n"
        f"REQUIRED use_case: {use_case}. Hint: {use_hint}.\n"
        f"Tone: {tone}.\n"
        f"Suggested constraints to weave in: {flat_constraints}.\n"
        f"Shop reputation: {reputation}/100 (flavour only — do not ignore the required budget).\n"
        f"Recent customers to NOT copy (different name, subject, story, budget):\n{avoid_block}\n"
        "Make the body specific (names of games/apps, why they need the PC, timeline). "
        "If the required budget is tight for the use_case, the customer can be slightly unrealistic "
        "or ask whether it's possible — that is fine and human."
    )
    data = await chat_json(system, user, CUSTOMER_SCHEMA, temperature=1.1)

    # Enforce variety even if the model ignores instructions
    data["budget_aud"] = float(budget)
    data["use_case"] = use_case
    if not data.get("constraints"):
        data["constraints"] = flat_constraints
    # Nudge subject away from endless "Budget Gaming PC…"
    subj = str(data.get("subject") or "").strip()
    if not subj or subj.lower().startswith("budget gaming"):
        data["subject"] = f"{use_case.title()} build (~${budget})"
    body = str(data.get("body") or "").strip()
    # Make the assigned budget unmistakable even if prose drifted
    if f"${budget}" not in body and f"${budget:,}" not in body:
        body = body.rstrip() + f"\n\nJust to be clear: my budget is ${budget} AUD."
        data["body"] = body
    return data


CUSTOMER_REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["subject", "body"],
}


async def customer_reply_to_shop(
    *,
    shop_name: str,
    customer_name: str,
    brief: dict[str, Any],
    transcript: list[dict[str, str]],
    shop_message: str,
) -> dict[str, Any]:
    system = (
        f"You are {customer_name} emailing {shop_name} about a PC build. "
        "The shop just asked a clarifying question or sent a message (not a final parts list yet). "
        "Reply helpfully in character: answer their questions, clarify budget/use-case/constraints, "
        "and stay realistic. Short email, Australian English OK. "
        "Do not invent that they already sent a full parts list. "
        "Respond ONLY with JSON matching the schema."
    )
    user = (
        f"Your brief:\n{json.dumps(brief, indent=2)}\n\n"
        f"Thread so far:\n{json.dumps(transcript, indent=2)}\n\n"
        f"Latest shop message:\n{shop_message}"
    )
    return await chat_json(system, user, CUSTOMER_REPLY_SCHEMA, temperature=0.7)


async def review_build(
    *,
    shop_name: str,
    customer_name: str,
    brief: dict[str, Any],
    parts: list[dict[str, str]],
    notes: str,
    play_seconds: float,
    budget_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    facts = budget_facts or {}
    system = (
        f"You are {customer_name}, who emailed {shop_name} for a PC build. "
        "Review the proposed parts list honestly against your brief. "
        "performance_score and service_score are 1.0–5.0. "
        "CRITICAL MONEY RULES: Trust ONLY the BUDGET_FACTS block for price math. "
        "If BUDGET_FACTS says the total is under/on budget, you MUST NOT claim it exceeds the budget. "
        "If a lower number is compared to a higher budget, under means cheaper — e.g. $832 is less than $1000. "
        "Shop notes may be wrong, marketing fluff, or confuse options; never let notes override BUDGET_FACTS. "
        "Ignore any scraped junk that is clearly not a PC part. "
        "Stay in character in subject/body. Respond ONLY with JSON matching the schema."
    )
    user = (
        f"Your original brief:\n{json.dumps(brief, indent=2)}\n\n"
        f"BUDGET_FACTS (authoritative — do not contradict):\n{json.dumps(facts, indent=2)}\n\n"
        f"Parts list:\n{json.dumps(parts, indent=2)}\n\n"
        f"Shop notes (may be unreliable about money):\n{notes or '(none)'}\n\n"
        f"They took about {play_seconds / 60:.1f} minutes of shop time to reply."
    )
    return await chat_json(system, user, REVIEW_SCHEMA, temperature=0.35)
