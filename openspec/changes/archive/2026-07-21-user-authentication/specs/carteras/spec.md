# Delta for carteras

## ADDED Requirements

### Requirement: Authenticated Cartera Access

The system MUST require an authenticated user for cartera creation, listing, and deletion, and MUST scope results to that user.

#### Scenario: List and create only within the caller account

- GIVEN an authenticated user
- WHEN the user lists carteras or creates a new cartera
- THEN the list contains only that user's carteras
- AND any new cartera is owned by that user

#### Scenario: Unauthenticated or foreign access is rejected

- GIVEN no valid session or a cartera owned by another user
- WHEN the client calls a protected cartera route
- THEN the system rejects the call
- AND deletion of a foreign cartera returns the same not-found behavior used for a missing cartera
