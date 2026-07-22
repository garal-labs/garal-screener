# user-authentication Specification

## Purpose

Define account access, session validation, and password recovery for backend clients.

## Requirements

### Requirement: Account Registration and Login

The system MUST let a new user register with a unique email and valid password, then log in with those credentials.

#### Scenario: Register and log in successfully

- GIVEN an email not yet registered
- WHEN the client submits valid registration data and later valid login data
- THEN the system creates the user and authenticates that user
- AND the authenticated response issues a session cookie

#### Scenario: Duplicate or invalid credentials are rejected

- GIVEN an existing email or wrong password
- WHEN the client attempts registration or login
- THEN the system rejects the request without authenticating a user

### Requirement: Cookie Session and Current User

The system MUST authenticate requests through a JWT stored in an httpOnly cookie and MUST expose the current authenticated user.

#### Scenario: Read current user from a valid session

- GIVEN a request with a valid auth cookie
- WHEN the client requests the current-user endpoint
- THEN the system returns that user's identity

#### Scenario: Missing or invalid session is denied

- GIVEN a request without a valid auth cookie
- WHEN the client requests a protected auth resource or logs out
- THEN the system denies protected access or clears the session safely

### Requirement: Password Reset

The system MUST support forgot-password and reset-password flows with single-use reset tokens.

#### Scenario: Start and complete password reset

- GIVEN a registered user
- WHEN the user requests a reset and then submits a valid unused token with a new password
- THEN the system accepts the new password and invalidates that token

#### Scenario: Expired or reused token fails

- GIVEN an expired, unknown, or already-used reset token
- WHEN the client submits a reset request with that token
- THEN the system rejects the reset
