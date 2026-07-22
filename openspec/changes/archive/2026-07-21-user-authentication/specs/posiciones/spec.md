# Delta for posiciones

## ADDED Requirements

### Requirement: Owner-Scoped Position Endpoints

The system MUST require authentication for cartera position, analysis, and FX backfill endpoints and MUST authorize them through cartera ownership.

#### Scenario: Owner reads analytics for own cartera

- GIVEN an authenticated user who owns a cartera
- WHEN the user requests resumen, analisis, or backfill-fx for that cartera
- THEN the system returns or mutates data only for that owned cartera

#### Scenario: Foreign cartera analytics are hidden

- GIVEN an authenticated user who does not own the target cartera
- WHEN the user requests any position-related cartera endpoint
- THEN the system responds as not found instead of revealing the cartera
