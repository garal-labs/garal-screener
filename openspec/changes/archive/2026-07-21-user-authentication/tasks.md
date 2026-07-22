# Tasks: User Authentication (Backend)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 560-720 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 foundation → PR2 auth flows → PR3 ownership + verification |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main (target branch: `develop`, not literal `main`) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 📍 | Models, schemas, deps, `app/auth/security.py`, migration | PR 1 → `develop` | Base = `develop`; add unit tests; merges to `develop` before PR 2 opens |
| 2 | `app/auth/router.py`, cookie session wiring, `main.py`, `tests/conftest.py` | PR 2 → `develop` | Base = `develop` (after PR 1 merged); depends on PR 1 |
| 3 | Owner scoping in `app/routers/{carteras,movimientos,posiciones}.py` + `tests/test_api.py` + migration check | PR 3 → `develop` | Base = `develop` (after PR 2 merged); depends on PR 2 |

## Phase 1: Foundation

- [x] 1.1 Modify `app/models.py` and `app/schemas.py` for `User`, `PasswordResetToken`, `Cartera.user_id`, and auth payload schemas.
- [x] 1.2 Create `app/auth/__init__.py` and `app/auth/security.py`; add hash/JWT helpers, `get_current_user`, `get_owned_cartera`.
- [x] 1.3 Update `requirements.txt` and create `alembic/versions/{rev}_add_user_auth.py` with batch add → backfill admin owner → `NOT NULL` → downgrade.

## Phase 2: Auth Flows

- [x] 2.1 Create `app/auth/router.py` for `register`, `login`, `logout`, `me`; set/clear `access_token` cookie per design contract.
- [x] 2.2 Implement forgot/reset flow in `app/auth/router.py` using hashed reset tokens, 1h TTL, and the single conditional consume update.
- [x] 2.3 Mount the auth router in `main.py` and keep explicit credentialed CORS behavior for dev/direct calls.

## Phase 3: Ownership Wiring

- [x] 3.1 Update `app/routers/carteras.py` so list/create/delete require `get_current_user` and scope all queries by owner.
- [x] 3.2 Update `app/routers/movimientos.py` to resolve the parent cartera through `get_owned_cartera` before create/list/delete and preserve 404-on-foreign behavior.
- [x] 3.3 Update `app/routers/posiciones.py` so `resumen`, `analisis`, and `backfill-fx` authorize through owned carteras, including the internal `resumen_cartera` call path.

## Phase 4: Verification

- [x] 4.1 Extend `tests/conftest.py` with `auth_client`; add `tests/test_auth_security.py` for hash and JWT valid/expired/tampered cases. (`auth_client` existed from PR2; extended with `second_auth_client` for owner-vs-foreign scenarios.)
- [x] 4.2 Expand `tests/test_api.py` for register/login/logout/me/reset and owner-vs-foreign scenarios across `carteras`, `movimientos`, and `posiciones`.
- [x] 4.3 Run `alembic upgrade head` and `alembic downgrade -1` on a scratch `cartera.db` copy to prove backfill, `NOT NULL`, and rollback behavior.
