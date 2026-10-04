# Markowitz Efficient Frontier

File locator: `odd/tasks/markowitz-efficient-frontier.md`
Engram mirror: `odd/markowitz-efficient-frontier/tasks`
Branch: `feat/markowitz-frontera-eficiente` (stacked on `chore/serena-setup`, PR #23)

## Objective

Expose an endpoint that analyses a portfolio's open positions with Markowitz mean-variance
theory: variance-covariance matrix, long-only efficient frontier, minimum-variance portfolio,
and where the current portfolio sits relative to the frontier.

## Problem / Why

The user models efficient portfolios by hand in a spreadsheet ("Markowitz - Cartera Eficiente.xlsx",
Google Drive). The app has no historical price series and no portfolio-risk analysis, so this
cannot be done for the real portfolio inside the product.

## Reference model (spreadsheet)

- Periodic (monthly) simple returns per asset, sample covariance (n-1 denominator).
- Closed-form, short-selling-allowed frontier: A = mu'S^-1 mu, B = 1'S^-1 mu, D = 1'S^-1 1;
  min-variance return = B/D, min variance = 1/D. No annualisation.
- This feature deliberately departs from the spreadsheet: **long-only** (0 <= w <= 1, sum w = 1),
  solved numerically. The closed form is kept only as a test oracle for the unconstrained case.

## Scope

- Backend only (`garal-screener`). Frontend chart is a separate future task in `investment-portfolio-ui`.
- Assets = open positions (quantity > 0) of an owned cartera.
- Monthly returns from yfinance adjusted close; lookback default 5 years (60 months), configurable.
- ~20 frontier points (configurable), minimum-variance portfolio, current portfolio point
  (weights = current EUR market value share of each position).

## Constraints

- Ownership: cartera fetched through the ownership-checked dependency (`get_owned_cartera`); foreign cartera -> 404.
- External price fetches batched (one yfinance download for all tickers), mocked in tests.
- Spanish domain naming in code/DB/schemas, consistent with the codebase.
- Add `numpy` and `scipy` to `requirements.txt` explicitly.
- Monthly figures, no annualisation (matches spreadsheet); expose the frequency in the response.

## Acceptance criteria

- `GET /api/v1/carteras/{cartera_id}/frontera-eficiente?anios=5&puntos=20` returns:
  tickers, covariance matrix, expected monthly returns, frontier points (return, volatility, weights),
  minimum-variance portfolio, current portfolio (return, volatility, weights).
- All frontier weights are in [0, 1] and sum to 1 (tolerance 1e-6).
- Minimum-variance volatility <= volatility of every frontier point and of the current portfolio.
- Fewer than 2 assets with usable history -> 422 with a clear message.
- Foreign or missing cartera -> 404.

## Tasks

- [x] T1 — Historical monthly price series: batch fetch of adjusted monthly closes in `app/services/precios.py` + tests with mocked yfinance.
- [ ] T2 — Pure Markowitz math service `app/services/markowitz.py` (returns, covariance, min-variance, long-only frontier via scipy SLSQP, portfolio stats) + deterministic tests (spreadsheet data as fixture; closed-form oracle for unconstrained case) + `numpy`/`scipy` in `requirements.txt`.
- [ ] T3 — Endpoint + schemas in `app/routers/posiciones.py` / `app/schemas.py`, wiring positions -> weights -> service, API tests (owner, foreign 404, <2 assets 422).

## Route declaration

- T1–T3: delegated direct (one writer). Trigger: writer trigger (2+ non-trivial files) and preparation trigger (reading routers/services/tests to prepare writes).

## Checks

- Focused: `.venv/bin/python -m pytest tests/test_precios.py tests/test_markowitz.py tests/test_api.py -q`
- Task closure: `make check` (ruff, black --check, mypy, full pytest)
- Test-first: RED before GREEN for each task where a deterministic test applies.

## Delivery

- Forecast: ~550-650 authored changed lines (T1 ~120, T2 ~250, T3 ~220) -> exceeds the ~400 budget.
- Strategy: ask-on-risk (default); chain strategy pending user answer.

## Progress / Evidence

- 2026-10-04: feature document created; branch created.
- 2026-10-04 T1 done (delegated writer). `obtener_precios_mensuales_batch(tickers, fecha_inicio, fecha_fin)
  -> dict[str, list[tuple[date, float]]]`: one `yf.download(interval="1mo", auto_adjust=True)`, dates
  normalised to the 1st of the month (latest row wins within a month), NaN dropped, tickers without
  data omitted, download errors logged -> `{}`. Handles flat (single ticker) and MultiIndex columns.
  RED: collection ImportError (`obtener_precios_mensuales_batch` missing). GREEN:
  `pytest tests/test_precios.py -q` -> 41 passed. Commit: see `git log` (`feat(precios): ...`).

## Next step

T2.
