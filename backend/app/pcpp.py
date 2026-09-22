from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .models import Part

logger = logging.getLogger(__name__)

LIST_RE = re.compile(
    r"^https?://(?:[a-z]{2}\.)?pcpartpicker\.com/list/([A-Za-z0-9]+)/?",
    re.IGNORECASE,
)
PRICE_RE = re.compile(r"\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)")
TOTAL_RE = re.compile(r"Total:\s*\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)", re.I)

# Category / compatibility chrome that is not a real part
JUNK_NAME_RE = re.compile(
    r"^(CPUs?\b|CPU Coolers?|Motherboards?|Memory Slots?|CPU Sockets?|CPU Cooler Mounts?"
    r"|Video Cards?|Power Supplies?|Cases?|Peripherals?|Disclaimer|CPU_SCKT|MOBO_MNT"
    r"|A Disclaimer|Wired Networking|Wireless Networking|Accessories)",
    re.I,
)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}


def validate_pcpp_url(url: str) -> str:
    url = url.strip()
    m = LIST_RE.match(url)
    if not m:
        raise ValueError("URL must be a PCPartPicker list link like https://au.pcpartpicker.com/list/XXXX")
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    list_id = m.group(1)
    return f"https://{host}/list/{list_id}"


def _clean_name(name: str) -> str:
    name = name.replace("\u200b", "").strip()
    # Drop PCPP custom-part disclaimer suffixes
    for marker in ("Note: The following custom part", "PCPartPicker cannot vouch"):
        if marker in name:
            name = name.split(marker, 1)[0].strip()
    return name


def _parse_money(text: str) -> float | None:
    m = PRICE_RE.search(text.replace(",", ""))
    if not m:
        m = PRICE_RE.search(text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _is_junk_part(name: str, ptype: str = "") -> bool:
    n = name.strip()
    if not n or len(n) < 3:
        return True
    if JUNK_NAME_RE.match(n):
        return True
    if "CPUs CPU Coolers Motherboards" in n:
        return True
    if n.lower() in ("name", "component", "price", "buy", "where"):
        return True
    # Category-only rows with no real product
    if ptype.lower() in ("", "component") and len(n) < 20 and " " not in n:
        return True
    return False


def _parse_parts_html(html: str) -> tuple[list[Part], float | None]:
    soup = BeautifulSoup(html, "lxml")
    parts: list[Part] = []

    # Current PCPP markup (2025+): product rows, not necessarily under table.partlist
    for row in soup.select("tr.tr__product"):
        type_el = row.select_one("td.td__component, .td__component")
        name_el = row.select_one("td.td__name a, .td__name a")
        if not name_el:
            name_el = row.select_one("td.td__name, .td__name")
        price_el = row.select_one("td.td__price, .td__price")

        ptype = type_el.get_text(" ", strip=True) if type_el else ""
        name = _clean_name(name_el.get_text(" ", strip=True) if name_el else "")
        price_raw = price_el.get_text(" ", strip=True) if price_el else ""
        price_raw = price_raw.replace("Price", "").strip()
        purl = ""
        if name_el and getattr(name_el, "get", None):
            href = name_el.get("href") or ""
            if href.startswith("/product/"):
                purl = "https://pcpartpicker.com" + href
            elif "/product/" in href:
                purl = href

        if _is_junk_part(name, ptype):
            continue
        parts.append(Part(type=ptype, name=name, price=price_raw, url=purl))

    total: float | None = None
    m = TOTAL_RE.search(soup.get_text(" ", strip=True))
    if m:
        total = float(m.group(1).replace(",", ""))
    elif parts:
        prices = [_parse_money(p.price) for p in parts]
        if all(p is not None for p in prices):
            total = round(sum(prices), 2)  # type: ignore[arg-type]

    return parts, total


async def _fetch_httpx(url: str) -> str:
    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(url)
        blocked = resp.status_code == 403 or "Attention Required" in resp.text
        if blocked or ("Just a moment" in resp.text and "cloudflare" in resp.text.lower()):
            raise RuntimeError("Cloudflare blocked simple fetch")
        resp.raise_for_status()
        return resp.text


async def _fetch_playwright(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError("Playwright not available for Cloudflare bypass") from e

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=BROWSER_HEADERS["User-Agent"])
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # Wait for the actual parts table, not just the shell
            try:
                await page.wait_for_selector("tr.tr__product", timeout=15000)
            except Exception:
                await page.wait_for_timeout(2500)
            return await page.content()
        finally:
            await browser.close()


async def resolve_list(url: str) -> dict[str, Any]:
    normalized = validate_pcpp_url(url)
    method = "httpx"
    try:
        html = await _fetch_httpx(normalized)
    except Exception as e:
        logger.warning("httpx PCPP fetch failed: %s — trying Playwright", e)
        method = "playwright"
        html = await _fetch_playwright(normalized)

    parts, total = _parse_parts_html(html)
    if not parts:
        raise RuntimeError(
            "Could not parse parts from PCPartPicker page. Paste the parts list text instead."
        )
    return {
        "url": normalized,
        "parts": [p.model_dump() for p in parts],
        "total_aud": total,
        "method": method,
    }


def parse_parts_text(text: str) -> tuple[list[Part], float | None]:
    """Parse pasted PCPP-style lines. Returns (parts, total_aud)."""
    parts: list[Part] = []
    total: float | None = None

    for raw in text.strip().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("total:"):
            total = _parse_money(line)
            continue
        if line.lower().startswith("pcpartpicker") or line.lower().startswith("prices include"):
            continue
        if line.lower().startswith("generated by"):
            continue

        # "CPU: Name ($65.00)" or "CPU: Name  ($65.00)"
        if ":" in line:
            ptype, rest = line.split(":", 1)
            ptype = ptype.strip()
            rest = rest.strip()
            # Skip obvious non-part headers
            if ptype.lower() in ("type", "component"):
                continue
            price = ""
            pm = re.search(r"\(\s*(\$\s*[0-9,.]+)\s*\)\s*$", rest)
            if pm:
                price = pm.group(1).replace(" ", "")
                rest = rest[: pm.start()].strip()
            else:
                pm2 = PRICE_RE.search(rest)
                if pm2 and rest.rfind("$") > 10:
                    # trailing price without parens
                    idx = rest.rfind("$")
                    maybe = rest[idx:]
                    if _parse_money(maybe) is not None and len(rest[:idx].strip()) > 5:
                        price = maybe.strip()
                        rest = rest[:idx].strip()
            name = _clean_name(rest)
            if _is_junk_part(name, ptype):
                continue
            parts.append(Part(type=ptype, name=name, price=price))
            continue

        if "\t" in line:
            bits = [b.strip() for b in line.split("\t") if b.strip()]
            if len(bits) >= 2:
                parts.append(
                    Part(
                        type=bits[0],
                        name=_clean_name(bits[1]),
                        price=bits[2] if len(bits) > 2 else "",
                    )
                )
            continue

        # Plain line with a price at the end
        name = _clean_name(line)
        if not _is_junk_part(name):
            parts.append(Part(name=name))

    if not parts:
        raise ValueError("No parts found in pasted text")

    if total is None:
        prices = [_parse_money(p.price) for p in parts]
        if prices and all(p is not None for p in prices):
            total = round(sum(p for p in prices if p is not None), 2)

    return parts, total


def parts_total_aud(parts: list[dict[str, Any]], explicit: float | None = None) -> float | None:
    if explicit is not None:
        return explicit
    prices = [_parse_money(str(p.get("price") or "")) for p in parts]
    if prices and all(p is not None for p in prices):
        return round(sum(p for p in prices if p is not None), 2)
    return None


def budget_facts(budget_aud: float | None, total_aud: float | None) -> dict[str, Any]:
    """Hard numbers for the reviewer — do not invent money math."""
    if budget_aud is None or total_aud is None:
        return {
            "budget_aud": budget_aud,
            "parts_total_aud": total_aud,
            "status": "unknown",
            "delta_aud": None,
            "summary": "Budget or total unknown — do not invent over/under-budget claims.",
        }
    delta = round(total_aud - float(budget_aud), 2)
    if delta <= 0:
        status = "under_or_on_budget"
        summary = (
            f"PARTS TOTAL ${total_aud:.2f} is UNDER/ON the customer budget of ${float(budget_aud):.2f} "
            f"(${abs(delta):.2f} under). This is NOT over budget."
        )
    else:
        status = "over_budget"
        summary = (
            f"PARTS TOTAL ${total_aud:.2f} is OVER the customer budget of ${float(budget_aud):.2f} "
            f"by ${delta:.2f}."
        )
    return {
        "budget_aud": float(budget_aud),
        "parts_total_aud": float(total_aud),
        "status": status,
        "delta_aud": delta,
        "summary": summary,
    }
