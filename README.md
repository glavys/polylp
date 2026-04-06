# polylp

Polymarket LP rewards scanner. Finds markets with thin order books inside the
rewards spread, so you can occupy the book and capture most of the
`rate_per_day` payout.

## Strategy

Polymarket distributes LP rewards proportional to each maker's share of
qualifying orders within `rewards_max_spread` of midpoint. So the edge is:

1. **Thin in-spread book** — you take a large share of the reward pool.
2. **Event not too soon** — whales haven't arrived to fill the book yet.
3. **Event not too late** — capital isn't locked for weeks at low marginal APR.

Default sweet spot: `6h ≤ hours_until_start ≤ 72h`.

## Metrics

- **APR** = `rate_per_day × 365 / (in_spread_liquidity + your_capital)`
- **Exp $/day** = `rate_per_day × your_capital / (in_spread_liquidity + your_capital)`
- **Liq in spread** — sum of share sizes within `rewards_max_spread` of
  midpoint across both YES/NO books (via CLOB `/books`). Falls back to gamma
  total liquidity for markets we didn't enrich.

## Data sources

- `gamma-api.polymarket.com/markets` — market list with `clobRewards`,
  `liquidityNum`, `volumeNum`, `gameStartTime`, fanout across several
  `(order, ascending)` combinations because the default order buries sports.
- `clob.polymarket.com/books` — actual order book for the top ~150 filtered
  candidates, used to compute real in-spread depth.

## Run

```
pip install httpx fastapi uvicorn jinja2
uvicorn polylp.server:app --host 127.0.0.1 --port 8787
```

Then open http://127.0.0.1:8787/

## Endpoints

- `GET /` — HTML dashboard with clickable column sorts and filter form.
- `GET /api/markets` — JSON. Query params: `min_hours`, `max_hours`,
  `min_rewards`, `max_rewards`, `max_liquidity`, `max_volume`, `max_min_size`,
  `sort` (`apr` / `expected` / `rate` / `liquidity` / `volume` / `hours` /
  `min_size` / `spread`), `dir` (`asc` / `desc`), `limit`.
