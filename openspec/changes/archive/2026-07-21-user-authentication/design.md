# Design: User Authentication (Backend)

> Companion design: `investment-portfolio-ui/openspec/changes/user-authentication/design.md` (frontend cookie/middleware handling).

## Technical Approach

Add a `User` model (`nombre` nullable) and an `app/auth/` package (security primitives + router), wire a `get_current_user` dependency into every cartera-scoped route, and add `carteras.user_id` via an Alembic batch migration that backfills legacy rows and then enforces `NOT NULL` in the same migration file. JWT lives only in an httpOnly/Secure/SameSite=Lax cookie, never the JSON body. Follows the existing router-per-domain pattern.

## Architecture Decisions

### Decision: JWT library

| Option | Tradeoff | Decision |
|---|---|---|
| `python-jose` | Unmaintained since 2021, CVEs | Rejected |
| `PyJWT` | Industry standard, widely supported | **Chosen** |
| `joserfc` | Maintained, already in `.venv` | Rejected |

### Decision: Password hashing

**Choice**: `passlib[bcrypt]` (proposal-mandated). **Alternatives**: raw `bcrypt`, `argon2-cffi`. **Rationale**: `CryptContext` gives a free hash-scheme upgrade path.

### Decision: Auth module boundary

**Choice**: `app/auth/` package — `security.py` (hash, JWT, `get_current_user`), `router.py` (endpoints). **Alternatives**: single `app/routers/auth.py` (proposal's literal path). **Rationale**: `get_current_user` is imported by every other router; putting it in `routers/` creates a reverse import. Deviation flagged in Open Questions.

### Decision: Ownership enforcement pattern

**Choice**: One dependency, `get_owned_cartera(cartera_id, user, db) -> Cartera`, reused by all three routers; 404 (not 403) on foreign cartera per spec. **Alternatives**: inline check per route — rejected, 8+ call sites, easy to miss one.

### Decision: Migration strategy

**Choice**: Alembic batch mode (required for SQLite `ADD COLUMN`+FK): in one migration file do (1) add nullable `user_id`+FK, insert system user, backfill `UPDATE carteras SET user_id = <system_id> WHERE user_id IS NULL`; then (2) run a second `batch_alter_table` step to alter `user_id` to `nullable=False`. **Rationale**: the ownership invariant is DB-enforced (`every cartera has one owner`); in SQLite batch mode already performs the table copy/rebuild, so doing the two-step pattern in the same migration has no extra structural cost. `downgrade()` reverses both steps.

## Data Flow

    POST /auth/login ──→ verify password ──→ issue JWT ──→ Set-Cookie (httpOnly, Secure, Lax)
                                                                    │
    /carteras* ──→ get_current_user (cookie→JWT→User) ──→ get_owned_cartera(cartera_id, user, db)
                                                                    │
                                                        404 if foreign, else Cartera (owned)
                                                        — reused by movimientos/posiciones routers

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/models.py` | Modify | Add `User` (`nombre` nullable), `PasswordResetToken` (`user_id` FK NOT NULL, `token_hash` UNIQUE indexed, `expires_at`, `used_at`); `user_id` FK + relationship on `Cartera` |
| `app/auth/__init__.py` | Create | Package marker |
| `app/auth/security.py` | Create | Hash/verify, token issue/decode, `get_current_user`, `get_owned_cartera` |
| `app/auth/router.py` | Create | `register` (accepts optional `nombre`), `login`, `logout`, `me`, `forgot-password`, `reset-password` (single-use token consume) endpoints |
| `app/schemas.py` | Modify | Add `UserCreate`/`UserOut` with optional `nombre`; `LoginRequest`, `ForgotPasswordRequest`, `ResetPasswordRequest` |
| `app/routers/carteras.py` | Modify | Inject `get_current_user`; filter by `user_id`; `get_owned_cartera` for delete |
| `app/routers/movimientos.py` | Modify | Inject auth; resolve cartera via `get_owned_cartera` before create/list/delete |
| `app/routers/posiciones.py` | Modify | Inject auth. Note: `analisis_cartera` calls `resumen_cartera` as a plain function today — forward `current_user` there too |
| `main.py` | Modify | Mount `auth_router`; production calls arrive via frontend server-side proxy/BFF, keep `allow_credentials=True` + explicit `ALLOWED_ORIGINS` as defense-in-depth for direct/dev browser calls |
| `alembic/versions/{rev}_add_user_auth.py` | Create | New tables + `user_id` FK migration in two batch steps (add nullable → backfill → alter to NOT NULL), with downgrade reversing both |
| `tests/conftest.py` | Modify | `auth_client` fixture: register+login, `TestClient` with session cookie |
| `requirements.txt` | Modify | Add `PyJWT`, `passlib[bcrypt]` |

## Interfaces / Contracts

```python
# app/auth/security.py
def hash_password(password: str) -> str: ...
def verify_password(password: str, hashed: str) -> bool: ...
def create_access_token(user_id: int, expires_minutes: int = 60 * 24 * 7) -> str: ...
def decode_access_token(token: str) -> int: ...  # user_id, raises on invalid/expired

def get_current_user(
    access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> models.User: ...

def get_owned_cartera(
    cartera_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Cartera: ...  # 404 if missing or not owned
```

New schemas follow the existing `CarteraCreate`/`CarteraOut` pattern: `UserCreate{email: EmailStr, password: str (min 8), nombre: str | None = None}`, `LoginRequest{email, password}`, `UserOut{id, email, nombre: str | None = None}` (`from_attributes=True`).

`PasswordResetToken` contract: columns MUST include `user_id` (FK to `users.id`, `NOT NULL`), `token_hash` (store hash only; never raw token; `UNIQUE` index), `expires_at` (1h TTL), `used_at` nullable.

`POST /auth/reset-password` consume step MUST be SQLite-safe and atomic via one conditional update:

```sql
UPDATE password_reset_tokens
SET used_at = :now
WHERE token_hash = :hash
  AND used_at IS NULL
  AND expires_at > :now;
```

Then require `rowcount == 1`. If `rowcount == 0`, return a generic invalid/expired/already-used token error (no reason leakage).

Cookie: `access_token`, `httponly=True`, `secure=True` (off only for `ENV=local` over http), `samesite="lax"`, `path="/"`, `max_age` matching JWT expiry.

`path="/"` is explicit for clarity (Starlette already defaults to it): frontend `middleware.ts` checks this cookie on page-route requests across the app (`/dashboard`, `/movimientos`, etc.), so a narrower path would cause false unauthenticated redirects.

CORS/deployment contract: in production, browser traffic targets the frontend origin and a same-origin frontend proxy/BFF forwards requests server-to-server to this API; direct cross-origin browser calls are non-primary. Backend still keeps `allow_credentials=True` and explicit `ALLOWED_ORIGINS` as defense-in-depth (including dev/direct modes).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Hash/verify, token issue/decode (valid, expired, tampered) | `tests/test_auth_security.py`, no DB |
| Integration | Register/login/logout/me, reset flow, routes reject unauthenticated + foreign-owner with 404 | `tests/test_api.py`, new `auth_client` fixture |
| Migration | Upgrade on a `cartera.db` copy → rows get system user and `carteras.user_id` ends as `NOT NULL`; `downgrade()` restores schema cleanly | Manual `upgrade head` / `downgrade -1` on scratch copy |

## Migration / Rollout

1. `alembic upgrade head`: creates `users`/`password_reset_tokens`; runs `carteras.user_id` in one migration file as add nullable FK → backfill to system user (`fjgarcia.alvarez@hotmail.com`) → alter to `NOT NULL`.
2. Run the migration during a brief maintenance window (or while write traffic is paused) so no cartera-creation write can race the backfill/constraint step.
3. Deploy backend with ownership enforcement live in the same release — no dual-write phase, low risk given single-user usage today.
4. Frontend companion change lands in the same window (removes hardcoded `cartera_id=1`).
5. Rollback: `alembic downgrade -1` reverses both `user_id` migration steps, drops the FK and both new tables; revert router changes.

## Open Questions

- [x] `app/auth/` package (this design) vs. proposal's literal `app/routers/auth.py` — accepted, no functional difference; avoids the reverse-import issue.
- [x] System/admin placeholder email for the backfilled owner — resolved: `fjgarcia.alvarez@hotmail.com`.
- [x] JWT/cookie lifetime — confirmed 7 days.
