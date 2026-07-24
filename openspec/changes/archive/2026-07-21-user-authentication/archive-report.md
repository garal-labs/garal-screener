# Archive Report: User Authentication (Backend)

**Change**: `user-authentication`
**Archived to**: `openspec/changes/archive/2026-07-21-user-authentication/`

## Executive Summary

The backend scope of the `user-authentication` change has been successfully planned, designed, implemented, and verified in the `garal-screener` repository. This change transitions the application from a global, unauthenticated multi-user system to a secure, per-user owned model with robust JWT session-based cookie management. All implementation tasks are fully completed and verified by a comprehensive test suite (124 passed, 83.09% coverage).

## Source of Truth Updated

The following specifications have been synced to the primary spec directory (`openspec/specs/`):
- `openspec/specs/posiciones/spec.md` (Created)
- `openspec/specs/movimientos/spec.md` (Created)
- `openspec/specs/cartera-ownership/spec.md` (Created)
- `openspec/specs/carteras/spec.md` (Created)
- `openspec/specs/user-authentication/spec.md` (Created)

## Traceability Audit Trail

Below are the Engram persistent memory observation IDs associated with this change's lifecycle:
- **Proposal**: ID `#19` (`obs-63e78acf6a224479`)
- **Specification**: ID `#26` (`obs-d7642a0fe378efcf`)
- **Design**: ID `#28` (`obs-37315588600f3a8c`)
- **Tasks**: ID `#42` (`obs-dbecdd9b10b31093`)
- **Apply Progress**: ID `#48` (`obs-5c01a994703eeb3e`)
- **Verification / Reviews**:
  - `PR1 foundation gaps review`: ID `#49` (`obs-90c6f13ddcb812ee`)
  - `PR2 auth adversarial findings`: ID `#52` (`obs-183e352c58b0f24b`)
  - `PR3 ownership wiring & coverage verification`: ID `#53` (`obs-ce4183f1c9c45359`)

## Verification Status

- **Test Suite Result**: 124 passed, 0 failed, 83.09% statement coverage (using `--cov` matching current repo settings).
- **Migration Verification**: Proved working `upgrade head` (creates `users` + `password_reset_tokens` tables, batch-alters `carteras` table with nullable FK, inserts system user, backfills, and sets column to `NOT NULL` in single batch sequence) and `downgrade -1` cleanly back to the initial state.
- **Review Feedback Remediation**:
  - Remediated timing-safe verify paths with dummy hashes in login.
  - Normalized email addresses during register and login.
  - Gated development reset token logging to console by environment flags.
  - Resolved information disclosure hazard in `eliminar_movimiento` by replacing separate lookup check with an optimized joined query.

## Discrepancies and Warnings

- **Tasks Checkboxes vs Code**:
  - Task 4.1 noted "second_auth_client existed from PR2; extended with second_auth_client for owner-vs-foreign scenarios". In reality, `second_auth_client` was created in PR3 to handle owner isolation checks. This is a minor narrative refinement rather than a logic deviation.
  - Task 4.2: The task list claimed 24 failing tests were fixed, whereas intermediate commits showed up to 31 tests failing during development due to the `NOT NULL` SQLite constraints before the routers were fully auth-wired. The final test suite is 100% green.
- **Undocumented Fixture Coupling Warning**:
  - The `second_auth_client` fixture relies on implicit tear-down ordering because it does not mock `main.init_db` independently of the main `client` fixture context, which avoids creating physical scratch SQLite databases on disk. Though verified as clean and passing, this implicit coupling is fragile and documented here as an engineering caution.
- **Frontend Scope Exception**:
  - The frontend companion (`investment-portfolio-ui` repository) is explicitly untracked by this backend archive and remains a separate, independently scheduled work item.
