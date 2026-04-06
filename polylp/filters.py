from __future__ import annotations

from typing import Optional

from .models import Market


def apply_filters(
    markets: list[Market],
    min_hours: float = 0.0,
    max_hours: Optional[float] = None,
    max_volume: Optional[float] = None,
    max_liquidity: Optional[float] = None,
    min_rewards: float = 0.0,
    max_rewards: Optional[float] = None,
    max_min_size: Optional[float] = None,
    require_start_time: bool = False,
) -> list[Market]:
    out = []
    for m in markets:
        if m.rate_per_day < min_rewards:
            continue
        if max_rewards is not None and m.rate_per_day > max_rewards:
            continue
        if max_volume is not None and m.volume > max_volume:
            continue
        if max_liquidity is not None and m.effective_liquidity > max_liquidity:
            continue
        if max_min_size is not None and m.rewards_min_size > max_min_size:
            continue
        h = m.hours_until_start
        if h is None:
            if require_start_time or min_hours > 0:
                continue
        else:
            if h < min_hours:
                continue
            if max_hours is not None and h > max_hours:
                continue
        out.append(m)
    return out


def score(m: Market) -> float:
    """APR (%) = rate_per_day * 365 / (in-spread liquidity + min_size).
    Uses CLOB in-spread depth if fetched, falls back to gamma total liquidity."""
    return m.apr * 100.0
