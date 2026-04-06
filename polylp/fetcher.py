"""Fetch Polymarket markets with LP rewards via Gamma API.

Gamma's default order omits many sports markets. We fan out across several
(order, ascending) combinations and union the results by conditionId to
cover both high-liquidity political markets and low-liquidity sports books.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx

from .models import Market

GAMMA_URL = "https://gamma-api.polymarket.com/markets"
CLOB_BOOKS_URL = "https://clob.polymarket.com/books"

_CACHE: dict[str, Any] = {"ts": 0.0, "markets": []}
_CACHE_TTL = 60.0

# (order, ascending) combinations to union.
_ORDERS = [
    ("liquidity", "false"),
    ("liquidity", "true"),
    ("volume", "false"),
    ("volume", "true"),
    ("startDate", "false"),
]
_PAGE_LIMIT = 500
_PAGES_PER_ORDER = 3  # up to 1500 per order


async def _fetch_page(
    client: httpx.AsyncClient, order: str, ascending: str, offset: int
) -> list[dict]:
    params = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "rewardsMinRate": "0.01",
        "limit": str(_PAGE_LIMIT),
        "offset": str(offset),
        "order": order,
        "ascending": ascending,
    }
    try:
        r = await client.get(GAMMA_URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return []


def _book_in_spread_shares(book: dict, max_spread_cents: float) -> tuple[float, Optional[float]]:
    """Return (total in-spread share size across both sides, midpoint).
    `max_spread_cents` is the rewards_max_spread value (e.g. 2.5 → 0.025 price units)."""
    bids = book.get("bids") or []
    asks = book.get("asks") or []

    def parse(levels):
        out = []
        for lv in levels:
            try:
                out.append((float(lv["price"]), float(lv["size"])))
            except (KeyError, ValueError, TypeError):
                continue
        return out

    bids = parse(bids)
    asks = parse(asks)
    if not bids or not asks:
        return 0.0, None
    best_bid = max(p for p, _ in bids)
    best_ask = min(p for p, _ in asks)
    if best_ask <= best_bid:
        return 0.0, None
    mid = (best_bid + best_ask) / 2.0
    cutoff = max_spread_cents / 100.0  # cents → price units
    total = 0.0
    for p, s in bids:
        if mid - p <= cutoff:
            total += s
    for p, s in asks:
        if p - mid <= cutoff:
            total += s
    return total, mid


async def _fetch_books(
    client: httpx.AsyncClient, token_ids: list[str]
) -> dict[str, dict]:
    """POST /books in chunks. Returns {asset_id: book}."""
    out: dict[str, dict] = {}
    chunk = 50
    for i in range(0, len(token_ids), chunk):
        payload = [{"token_id": t} for t in token_ids[i : i + chunk]]
        try:
            r = await client.post(CLOB_BOOKS_URL, json=payload, timeout=20)
            r.raise_for_status()
            for b in r.json():
                aid = b.get("asset_id")
                if aid:
                    out[aid] = b
        except httpx.HTTPError:
            continue
    return out


async def _enrich_with_book_depth(
    client: httpx.AsyncClient, markets: list[Market]
) -> None:
    """For each market, fetch CLOB books for its tokens and compute in-spread
    liquidity (share sum within rewards_max_spread of midpoint, both sides,
    across both YES/NO tokens). Mutates markets in place."""
    all_tokens: list[str] = []
    for m in markets:
        all_tokens.extend(m.token_ids)
    if not all_tokens:
        return
    books = await _fetch_books(client, all_tokens)
    for m in markets:
        total = 0.0
        mid = None
        for tid in m.token_ids:
            b = books.get(tid)
            if not b:
                continue
            t, mp = _book_in_spread_shares(b, m.rewards_max_spread)
            total += t
            if mid is None:
                mid = mp
        # If we got no book data at all, leave as None so UI falls back to gamma.
        if mid is not None:
            m.liquidity_in_spread = total
            m.midpoint = mid


async def fetch_markets(force: bool = False, enrich_depth: bool = True) -> list[Market]:
    now = time.time()
    if not force and _CACHE["markets"] and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["markets"]

    async with httpx.AsyncClient() as client:
        tasks = [
            _fetch_page(client, order, asc, off * _PAGE_LIMIT)
            for order, asc in _ORDERS
            for off in range(_PAGES_PER_ORDER)
        ]
        pages = await asyncio.gather(*tasks)

        by_id: dict[str, dict] = {}
        for page in pages:
            for m in page:
                cid = m.get("conditionId")
                if cid:
                    by_id[cid] = m

        markets = [Market.from_gamma(m) for m in by_id.values() if Market.has_rate(m)]

        if enrich_depth:
            # Only enrich the most promising candidates (thin books, reasonable
            # time window, non-trivial rate) so we don't hammer CLOB.
            candidates = [
                m for m in markets
                if m.liquidity < 20000
                and m.rate_per_day >= 1
                and (m.hours_until_start is None or 0 < m.hours_until_start < 24 * 14)
                and m.token_ids
            ]
            candidates.sort(key=lambda x: -x.rate_per_day / (x.liquidity + x.rewards_min_size + 1))
            await _enrich_with_book_depth(client, candidates[:150])

    _CACHE["markets"] = markets
    _CACHE["ts"] = now
    return markets


def fetch_markets_sync(force: bool = False) -> list[Market]:
    return asyncio.run(fetch_markets(force=force))
