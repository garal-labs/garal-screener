# Proposal: User Authentication (Backend)

> Cross-repo. Companion: `investment-portfolio-ui/openspec/changes/user-authentication/proposal.md`.

## Intent

Carteras are global/unowned today (frontend hardcodes `cartera_id=1`; any client can read/write any cartera). Add per-user ownership: open registration, login, password recovery — one cartera, one owner.

## Scope

### In Scope
- `User` + `PasswordResetToken` models; Alembic migration adding `user_id` FK (SQLite batch mode)
- Data migration: system/admin user owns ALL existing carteras (incl. legacy id 1)
- Password hashing (bcrypt); endpoints: register, login, logout, me, forgot/reset-password
- JWT issue/verify; `get_current_user` dependency
- Ownership enforcement on `carteras`, `movimientos`, `posiciones`; auth test fixtures

### Out of Scope
- Sharing/multi-owner, roles/admin panel, OAuth/social login, 2FA

## Capabilities

### New Capabilities
- `user-authentication`: register/login/logout/JWT/password reset/current-user
- `cartera-ownership`: per-user ownership across carteras + dependents

### Modified Capabilities
- `carteras`, `movimientos`, `posiciones`: require auth, filter by owner

## Approach

JWT via **httpOnly, Secure, SameSite=Lax cookie** (never JSON) — XSS-safe, pairs with Next.js middleware. CORS: `allow_credentials=True`, explicit origin.

`get_current_user` verifies the cookie, injected in cartera-scoped routes; each filters by owner (404 on mismatch, avoid leaking existence).

**Password reset**: dev/CI stub logs the link to console (zero-cost, unblocks now); real SMTP/provider is a deployment prerequisite, not built here — expands scope vs. login-only, flagged explicitly.

**Migration**: Alembic batch mode (SQLite needs it for ADD COLUMN+FK); nullable `user_id`, backfill with system user id, enforce required at app layer.

> Note (superseded by design): final design enforces `carteras.user_id` as `NOT NULL` at DB level, not app-layer only. See `design.md` for the definitive migration strategy.

## Affected Areas

| Area | Impact |
|------|--------|
| `app/models.py` | Add `User`, `PasswordResetToken`; FK on `Cartera` |
| `app/routers/auth.py` | New auth endpoints |
| `carteras.py`, `movimientos.py`, `posiciones.py` | Require auth + filter by owner |
| `app/auth/security.py` | New: hashing, JWT, `get_current_user` |
| `alembic/versions/` | New migration + backfill |
| `tests/conftest.py` | Authenticated client fixture |
| `requirements.txt` | Add `passlib[bcrypt]`, JWT lib |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|--------------|
| SQLite ADD COLUMN+FK migration fails/corrupts data | Medium | Batch mode; test on prod-shaped copy; require `downgrade()` |
| Password-reset expands scope (email infra) | Medium | Dev log-stub now; real provider = separate deploy prerequisite |
| Legacy `cartera_id=1` / cookie-CORS misconfig | Low-Med | Document admin id, coordinate frontend release; verify `allow_credentials` + origin before merge |

## Rollback Plan

Alembic `downgrade()` drops new tables/column; revert routers to remove auth dependency — restores pre-change global access. Mandatory, not optional.

## Dependencies

- Frontend companion must land in the same window.

## Success Criteria

- [ ] Register → login → httpOnly cookie works
- [ ] All existing carteras owned by migrated admin user
- [ ] Cartera-scoped endpoints reject unauthenticated requests, never leak other users' data
- [ ] Forgot/reset-password works end-to-end (dev: via logged token)
- [ ] Migration has a tested, working `downgrade()`
