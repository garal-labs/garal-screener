# Delta for movimientos

## ADDED Requirements

### Requirement: Owner-Scoped Movimiento Operations

The system MUST require authentication for movimiento creation, listing, and deletion, and MUST authorize each operation through the owner of the parent cartera.

#### Scenario: Owner manages movimientos in own cartera

- GIVEN an authenticated user who owns a cartera
- WHEN the user creates, lists, or deletes movimientos for that cartera
- THEN the system applies the operation only within that owned cartera

#### Scenario: Foreign cartera references are hidden

- GIVEN an authenticated user who does not own the target cartera or movimiento
- WHEN the user calls a movimiento route for that foreign resource
- THEN the system responds as not found instead of exposing another user's data
