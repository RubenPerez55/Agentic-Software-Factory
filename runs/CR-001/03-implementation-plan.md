# Implementation Plan — CR-001 (Event Waitlist)

## Scope

### In Scope
- Update domain models (`Event`, `Registration`) to support registration status (`ACTIVE` vs `WAITLISTED`).
- Update repository methods and schema (`registrations` table status column, FIFO ordering/filtering by status) adhering strictly to `API -> Service -> Repository` (NFR-01).
- Update service business logic:
  - Registrations when capacity is available become `ACTIVE`.
  - Registrations when capacity is full become `WAITLISTED` (FIFO order based on ID/insertion sequence).
  - Cancellations of `ACTIVE` participants automatically promote the first waiting `WAITLISTED` user to `ACTIVE`.
- Update API adapter and error responses if needed.
- Add deterministic automated tests verifying AC-CR001.1 through AC-CR001.5 (NFR-02).

### Out of Scope
- Duplicate registration prevention (deferred to CR-003).
- Authorization / organizer role validation changes.
- External infrastructure changes (in-memory / SQLite SQLiteCampusFlowRepository remains).
- Documentation updates to `docs/SPEC.md` (SPECs are product/owner documentation and are handled separately from code changes per architectural guidelines).

---

## Implementation Tasks

### `TASK-1`: Domain and Repository Updates for Registration Status
- **Files**:
  - `campusflow/domain.py`
  - `campusflow/repository.py`
- **Covers**: AC-CR001.1, AC-CR001.2, AC-CR001.3, AC-CR001.4, AC-CR001.5
- **Description**:
  - Add status field/enum/constant to `Registration` (e.g. `status: str` with values `"ACTIVE"` and `"WAITLISTED"`).
  - Update `registrations` table schema in `SQLiteCampusFlowRepository` to include a `status` column (defaulting to `"ACTIVE"` or explicitly inserting `"ACTIVE"` / `"WAITLISTED"`).
  - Provide repository query helpers to count/list active vs waitlisted registrations, find the first waitlisted user for an event (FIFO order by registration ID), and update a registration status upon promotion.

### `TASK-2`: Service Layer Business Logic for Waitlist and Promotion
- **Files**:
  - `campusflow/service.py`
- **Covers**: AC-CR001.1, AC-CR001.2, AC-CR001.3, AC-CR001.4, AC-CR001.5
- **Description**:
  - In `CampusFlowService.register`, check active registration count against `event.capacity`.
  - If active count `< event.capacity`, create registration with status `"ACTIVE"`.
  - If active count `>= event.capacity`, create registration with status `"WAITLISTED"`.
  - In `CampusFlowService.cancel`, if an `ACTIVE` registration is removed, query the first `"WAITLISTED"` registration for that event in FIFO order and update its status to `"ACTIVE"`.

### `TASK-3`: API Adapter Adjustments (if needed)
- **Files**:
  - `campusflow/api.py`
- **Covers**: AC-CR001.5
- **Description**:
  - Ensure registration response models or return values correctly expose the registration status (`ACTIVE` vs `WAITLISTED`) and HTTP status codes remain appropriate (201 Created for registrations whether active or waitlisted).

---

## Tests to Add or Change

- **Test to Change**: `tests/product/test_service.py` (`test_registration_rejects_when_event_is_full`)
  - **Reason**: The baseline test asserting `CapacityReachedError` conflicts with CR-001 (which replaces capacity rejection with waitlisting per AC-CR001.2 and REQUIREMENTS.md).
  - **Covers**: AC-CR001.2
- **Tests to Add**:
  - `test_registration_waitlisted_when_event_full`: Verifies that registrations when capacity is reached return `WAITLISTED` status.
  - `test_waitlist_fifo_order`: Verifies multiple overflow registrations are waitlisted in strict FIFO order.
  - `test_cancellation_promotes_first_waiting_user`: Verifies canceling an active participant promotes the earliest waitlisted user to active.
  - `test_baseline_behavior_regression`: Verifies basic event creation, listing, and below-capacity registration continue to work seamlessly.

---

## Existing Tests in Conflict (requiring Tech Lead decision)
1. **`tests/product/test_service.py` (`test_registration_rejects_when_event_is_full`)**:
   - *Proposal*: Replace or update this test to `test_registration_waitlisted_when_event_full` verifying that registrations when capacity is full result in status `WAITLISTED` instead of raising `CapacityReachedError`, as explicitly authorized by CR-001 and `REQUIREMENTS.md`.

---

## Architecture Constraints
- **NFR-01 (Architecture)**: Business logic resides exclusively in `CampusFlowService`. Repositories perform data persistence/queries only; API adapters handle routing/serialization.
- **Dependency Direction**: `API -> Service -> Repository`.

---

## Security Considerations
- No secrets introduced.
- Input validation on event creation and registration remains intact.

---

## Verification Commands
```bash
uv run pytest
uv run ruff check .
```

---

## Assumptions & Open Questions
- **Assumptions**:
  - Capacity counts only `ACTIVE` registrations.
  - Waitlist queue ordering is strictly FIFO based on registration ID (insertion order).
- **Open Questions (for Product Owner at Gate 1)**:
  - Can a user currently on the waitlist cancel their waitlist entry directly, and does that affect queue positions of others?
  - Should the API response for registration return an explicit `status` field in the JSON body?

---

## Context Used
- `docs/REPO_MAP.md`
- `runs/CR-001/00-change-request.md`
- `docs/REQUIREMENTS.md`
- `docs/SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/factory/CR-001-readiness.md`
- `runs/CR-001/01-intake-report.md`
- `campusflow/domain.py`
- `campusflow/repository.py`
- `campusflow/service.py`
- `campusflow/api.py`
- `tests/product/test_service.py`

```json
{
  "scope": {
    "in": [
      "Update Event and Registration domain models and SQLite repository schema/queries to support ACTIVE and WAITLISTED status",
      "Update Service business logic for capacity check, waitlist queueing (FIFO), and automatic promotion on cancellation",
      "Update API response serialization and error handling",
      "Add automated tests covering AC-CR001.1 through AC-CR001.5"
    ],
    "out": [
      "Duplicate registration prevention (CR-003)",
      "Organizer authorization rules",
      "External database infrastructure changes",
      "Documentation edits to SPEC.md"
    ]
  },
  "tasks": [
    {
      "id": "TASK-1",
      "description": "Update domain models and SQLite repository schema/queries to support registration status and FIFO waitlist operations.",
      "files": [
        "campusflow/domain.py",
        "campusflow/repository.py"
      ],
      "covers": [
        "AC-CR001.1",
        "AC-CR001.2",
        "AC-CR001.3",
        "AC-CR001.4",
        "AC-CR001.5"
      ]
    },
    {
      "id": "TASK-2",
      "description": "Implement service business rules for capacity evaluation, WAITLISTED registration when full, and FIFO promotion upon cancellation of active participants.",
      "files": [
        "campusflow/service.py"
      ],
      "covers": [
        "AC-CR001.1",
        "AC-CR001.2",
        "AC-CR001.3",
        "AC-CR001.4",
        "AC-CR001.5"
      ]
    },
    {
      "id": "TASK-3",
      "description": "Ensure API adapter correctly exposes registration status and status codes.",
      "files": [
        "campusflow/api.py"
      ],
      "covers": [
        "AC-CR001.5"
      ]
    }
  ],
  "tests_to_add_or_change": [
    {
      "test": "tests/product/test_service.py:test_registration_rejects_when_event_is_full -> test_registration_waitlisted_when_event_full",
      "reason": "AC-03.3 is intentionally replaced by CR-001 waitlist behavior, superseding CapacityReachedError on full events.",
      "covers": [
        "AC-CR001.2"
      ]
    },
    {
      "test": "tests/product/test_service.py:test_waitlist_fifo_order",
      "reason": "Verifies FIFO ordering for multiple overflow registrations.",
      "covers": [
        "AC-CR001.3"
      ]
    },
    {
      "test": "tests/product/test_service.py:test_cancellation_promotes_first_waiting_user",
      "reason": "Verifies automatic promotion of the first waiting user when an active participant cancels.",
      "covers": [
        "AC-CR001.4"
      ]
    }
  ],
  "existing_tests_in_conflict": [
    {
      "test": "tests/product/test_service.py:test_registration_rejects_when_event_is_full",
      "proposal": "Replace with a test verifying that full events result in WAITLISTED status per CR-001."
    }
  ],
  "architecture_constraints": [
    "NFR-01: Business rules live in Service. Dependency direction API -> Service -> Repository.",
    "Repository does not decide business logic."
  ],
  "security_considerations": [
    "No secrets stored in code.",
    "Input validation maintained."
  ],
  "verification_commands": [
    "uv run pytest",
    "uv run ruff check ."
  ],
  "assumptions": [
    "Capacity counts only ACTIVE registrations.",
    "Waitlist queue ordering is strictly FIFO based on registration ID (insertion sequence)."
  ],
  "open_questions": [
    "Can a user on the waitlist cancel their waitlisted entry directly?",
    "Should registration status be explicitly serialized in API response bodies?"
  ],
  "context_used": [
    "docs/REPO_MAP.md",
    "runs/CR-001/00-change-request.md",
    "docs/REQUIREMENTS.md",
    "docs/SPEC.md",
    "docs/ARCHITECTURE.md",
    "docs/factory/CR-001-readiness.md",
    "runs/CR-001/01-intake-report.md",
    "campusflow/domain.py",
    "campusflow/repository.py",
    "campusflow/service.py",
    "campusflow/api.py",
    "tests/product/test_service.py"
  ]
}
```