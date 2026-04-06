from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Optional


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(" ", "T")
    if s.endswith("+00"):
        s = s[:-3] + "+00:00"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _rate_from_gamma(m: dict) -> float:
    cr = m.get("clobRewards") or []
    if not cr:
        return 0.0
    # sum all active rewards configs (usually 1)
    total = 0.0
    for x in cr:
        total += float(x.get("rewardsDailyRate") or 0)
    return total


@dataclass
class Market:
    condition_id: str
    question: str
    market_slug: str
    event_slug: str
    rate_per_day: float
    rewards_max_spread: float
    rewards_min_size: float
    spread: float
    liquidity: float
    volume: float
    start_time: Optional[datetime]
    # CLOB token ids (YES, NO) — needed to fetch orderbook for in-spread depth
    token_ids: tuple = ()
    # Populated by optional book-depth enrichment; None until fetched.
    liquidity_in_spread: Optional[float] = None
    midpoint: Optional[float] = None

    @property
    def effective_liquidity(self) -> float:
        """In-spread liquidity if we fetched the book, else total gamma liquidity."""
        return self.liquidity_in_spread if self.liquidity_in_spread is not None else self.liquidity

    @property
    def expected_daily(self) -> float:
        """$/day the user would earn assuming they post `min_size` into current book."""
        denom = self.effective_liquidity + self.rewards_min_size
        if denom <= 0:
            return 0.0
        return self.rate_per_day * self.rewards_min_size / denom

    @property
    def apr(self) -> float:
        """Annualized yield on capital = rate * 365 / (in-spread liq + min_size).
        Time cancels out since both earnings and capital-days scale with hold time."""
        denom = self.effective_liquidity + self.rewards_min_size
        if denom <= 0 or self.rewards_min_size <= 0:
            return 0.0
        return self.rate_per_day * 365.0 / denom

    @staticmethod
    def has_rate(gamma: dict) -> bool:
        return _rate_from_gamma(gamma) > 0

    @property
    def url(self) -> str:
        slug = self.event_slug or self.market_slug
        return f"https://polymarket.com/event/{slug}" if slug else ""

    @property
    def hours_until_start(self) -> Optional[float]:
        if not self.start_time:
            return None
        now = datetime.now(timezone.utc)
        return (self.start_time - now).total_seconds() / 3600.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start_time"] = self.start_time.isoformat() if self.start_time else None
        d["url"] = self.url
        d["hours_until_start"] = self.hours_until_start
        d["apr"] = self.apr
        d["expected_daily"] = self.expected_daily
        d["effective_liquidity"] = self.effective_liquidity
        return d

    @classmethod
    def from_gamma(cls, m: dict) -> "Market":
        # clobTokenIds is a JSON-encoded string: '["tok1","tok2"]'
        tok_raw = m.get("clobTokenIds") or ""
        token_ids: tuple = ()
        if tok_raw:
            try:
                import json as _json
                parsed = _json.loads(tok_raw) if isinstance(tok_raw, str) else tok_raw
                if isinstance(parsed, list):
                    token_ids = tuple(str(t) for t in parsed if t)
            except Exception:
                pass
        events = m.get("events") or []
        event_slug = ""
        if events and isinstance(events, list):
            event_slug = events[0].get("slug") or ""
        # Prefer real game start time. Fallback to end/resolution date so the
        # "until" column makes sense for non-sports markets. `startDate` is the
        # market creation date — NOT useful here, ignore it.
        start_time = (
            _parse_dt(m.get("gameStartTime"))
            or _parse_dt(m.get("endDateIso"))
            or _parse_dt(m.get("endDate"))
        )
        return cls(
            condition_id=str(m.get("conditionId") or ""),
            question=str(m.get("question") or ""),
            market_slug=str(m.get("slug") or ""),
            event_slug=event_slug,
            rate_per_day=_rate_from_gamma(m),
            rewards_max_spread=float(m.get("rewardsMaxSpread") or 0),
            rewards_min_size=float(m.get("rewardsMinSize") or 0),
            spread=float(m.get("spread") or 0),
            liquidity=float(m.get("liquidityNum") or m.get("liquidity") or 0),
            volume=float(m.get("volumeNum") or m.get("volume") or 0),
            start_time=start_time,
            token_ids=token_ids,
        )
