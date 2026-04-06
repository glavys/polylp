from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .fetcher import fetch_markets
from .filters import apply_filters, score

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="Polymarket LP Rewards Scanner")


def _opt_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


SORT_KEYS = {
    "apr": (lambda m: m.apr, True),
    "expected": (lambda m: m.expected_daily, True),
    "rate": (lambda m: m.rate_per_day, True),
    "liquidity": (lambda m: m.effective_liquidity, False),
    "volume": (lambda m: m.volume, False),
    "hours": (lambda m: m.hours_until_start if m.hours_until_start is not None else 1e12, False),
    "min_size": (lambda m: m.rewards_min_size, False),
    "spread": (lambda m: m.rewards_max_spread, True),
}


async def _get_filtered(
    min_hours: float,
    max_hours: Optional[float],
    max_volume: Optional[float],
    max_liquidity: Optional[float],
    min_rewards: float,
    max_rewards: Optional[float],
    max_min_size: Optional[float],
    sort: str,
    sort_dir: str,
    limit: int,
):
    markets = await fetch_markets()
    filtered = apply_filters(
        markets,
        min_hours=min_hours,
        max_hours=max_hours,
        max_volume=max_volume,
        max_liquidity=max_liquidity,
        min_rewards=min_rewards,
        max_rewards=max_rewards,
        max_min_size=max_min_size,
    )
    key_fn, default_desc = SORT_KEYS.get(sort, SORT_KEYS["apr"])
    if sort_dir in ("asc", "desc"):
        reverse = sort_dir == "desc"
    else:
        reverse = default_desc
    filtered.sort(key=key_fn, reverse=reverse)
    return filtered[:limit], len(markets)


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    min_hours: Optional[str] = Query("6"),
    max_hours: Optional[str] = Query("72"),
    max_volume: Optional[str] = Query(None),
    max_liquidity: Optional[str] = Query(None),
    min_rewards: Optional[str] = Query("0"),
    max_rewards: Optional[str] = Query(None),
    max_min_size: Optional[str] = Query(None),
    sort: str = Query("apr"),
    dir: str = Query(""),
    limit: int = Query(50),
    refresh: int = Query(60),
):
    mh = _opt_float(min_hours) or 0.0
    mr = _opt_float(min_rewards) or 0.0
    filtered, total = await _get_filtered(
        mh,
        _opt_float(max_hours),
        _opt_float(max_volume),
        _opt_float(max_liquidity),
        mr,
        _opt_float(max_rewards),
        _opt_float(max_min_size),
        sort,
        dir,
        limit,
    )
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "markets": filtered,
            "total": total,
            "shown": len(filtered),
            "score": score,
            "params": {
                "min_hours": mh,
                "max_hours": max_hours or "",
                "max_volume": max_volume or "",
                "max_liquidity": max_liquidity or "",
                "min_rewards": mr,
                "max_rewards": max_rewards or "",
                "max_min_size": max_min_size or "",
                "sort": sort,
                "dir": dir,
                "limit": limit,
                "refresh": refresh,
            },
        },
    )


@app.get("/api/markets")
async def api_markets(
    min_hours: Optional[str] = "6",
    max_hours: Optional[str] = "72",
    max_volume: Optional[str] = None,
    max_liquidity: Optional[str] = None,
    min_rewards: Optional[str] = "0",
    max_rewards: Optional[str] = None,
    max_min_size: Optional[str] = None,
    sort: str = "apr",
    dir: str = "",
    limit: int = 100,
):
    filtered, total = await _get_filtered(
        _opt_float(min_hours) or 0.0,
        _opt_float(max_hours),
        _opt_float(max_volume),
        _opt_float(max_liquidity),
        _opt_float(min_rewards) or 0.0,
        _opt_float(max_rewards),
        _opt_float(max_min_size),
        sort,
        dir,
        limit,
    )
    return JSONResponse(
        {
            "total": total,
            "shown": len(filtered),
            "markets": [
                {**m.to_dict(), "score": round(score(m), 4)} for m in filtered
            ],
        }
    )
