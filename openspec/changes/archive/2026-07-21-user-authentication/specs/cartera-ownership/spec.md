# cartera-ownership Specification

## Purpose

Define who owns each cartera and how ownership constrains dependent data.

## Requirements

### Requirement: Cartera Ownership Assignment

The system MUST associate every cartera with exactly one user owner.

#### Scenario: New cartera gets the creator as owner

- GIVEN an authenticated user creates a cartera
- WHEN the create request succeeds
- THEN the cartera is stored with that user as owner

#### Scenario: Legacy carteras are assigned during migration

- GIVEN pre-auth carteras already exist
- WHEN the ownership migration runs
- THEN each existing cartera is assigned to the designated system/admin user

### Requirement: Ownership Applies to Dependent Data

The system MUST treat movimientos and posiciones as visible only through the owner of their parent cartera.

#### Scenario: Owner can access dependent data

- GIVEN a cartera owned by the authenticated user
- WHEN the user requests movimientos or position-based endpoints for that cartera
- THEN the system returns only data derived from that cartera

#### Scenario: Non-owner cannot observe another cartera

- GIVEN a cartera owned by a different user
- WHEN another authenticated user references that cartera or its dependent records
- THEN the system denies the request without confirming that the cartera exists
