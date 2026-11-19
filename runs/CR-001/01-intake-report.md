- Requested Outcome: Implement event waitlist behavior for CR-001 so that when an event reaches capacity, new registrations enter a waitlist (status `WAITLISTED`) instead of being rejected, and cancellations automatically promote the first waiting user.
- Affected Requirements: `FR-03` (AC-03.3 explicitly changed by CR-001), `FR-04`, `NFR-01`, `NFR-02`.
- Acceptance Criteria:
  - AC-CR001.1: below capacity remains active.
  - AC-CR001.2: full event -> WAITLISTED.
  - AC-CR001.3: waitlist is FIFO.
  - AC-CR001.4: cancellation promotes first waiting user.
  - AC-CR001.5: baseline event/list behavior does not regress.
- Likely Repository Areas:
  - `campusflow/domain.py`
  - `campusflow/repository.py`
  - `campusflow/service.py`
  - `campusflow/api.py`
  - `tests/product/`
- Ambiguities:
  - Question: "Can a user currently on the waitlist cancel their registration/waitlist entry?"
    Why it matters: The change request states "When an active participant cancels, the first waiting user is promoted," but does not specify whether waitlisted users can cancel directly or how that affects queue position.
  - Question: "How is registration status exposed in API / Domain objects (`ACTIVE` vs `WAITLISTED`)?"
    Why it matters: Affects domain model attributes, serialization in the FastAPI adapter, and verification tests.
- Conflicts:
  - Item: `tests/product/test_service.py` (specifically test expecting `CapacityReachedError` when event is full).
    Evidence: `REQUIREMENTS.md` states "CR-001 intentionally changes AC-03.3 by introducing a waitlist," conflicting with the existing test asserting capacity rejection.
  - Item: `docs/SPEC.md` under Register (states full capacity -> `CapacityReachedError`).
    Evidence: `SPEC.md` describes the old capacity rejection behavior overridden by CR-001.
- Context Used:
  - `docs/REPO_MAP.md`
  - `change_requests/CR-001-waitlist.md`
  - `docs/REQUIREMENTS.md`
  - `docs/SPEC.md`
  - `docs/ARCHITECTURE.md`
  - `docs/factory/CR-001-readiness.md`
- Recommendation: `PROCEED` (The core requirements and intentional override of AC-03.3 are explicitly defined in `REQUIREMENTS.md` and the change request, while minor operational questions can be handled during planning/Gate 1).

```json
{
  "requested_outcome": "Implement event waitlist behavior where registrations when full become WAITLISTED instead of rejected, and cancellations promote the first waiting user.",
  "affected_requirements": [
    "FR-03 (AC-03.3 changed by CR-001)",
    "FR-04",
    "NFR-01",
    "NFR-02"
  ],
  "acceptance_criteria": [
    "AC-CR001.1: below capacity remains active.",
    "AC-CR001.2: full event -> WAITLISTED.",
    "AC-CR001.3: waitlist is FIFO.",
    "AC-CR001.4: cancellation promotes first waiting user.",
    "AC-CR001.5: baseline event/list behavior does not regress."
  ],
  "likely_areas": [
    "campusflow/domain.py",
    "campusflow/repository.py",
    "campusflow/service.py",
    "campusflow/api.py",
    "tests/product/"
  ],
  "ambiguities": [
    {
      "question": "Can a user on the waitlist cancel their waitlisted entry?",
      "why_it_matters": "The change request covers active participant cancellation and promotion, but does not specify cancellation behavior or queue impact for waitlisted users."
    },
    {
      "question": "How should registration status be exposed in the domain and API?",
      "why_it_matters": "Determines model attributes and API response structures for ACTIVE vs WAITLISTED registrations."
    }
  ],
  "conflicts": [
    {
      "item": "tests/product/test_service.py (capacity reached test)",
      "evidence": "REQUIREMENTS.md states 'CR-001 intentionally changes AC-03.3 by introducing a waitlist', conflicting with existing tests asserting `CapacityReachedError`."
    },
    {
      "item": "docs/SPEC.md (Register section)",
      "evidence": "SPEC.md specifies that full capacity raises `CapacityReachedError`, which is superseded by CR-001."
    }
  ],
  "context_used": [
    "docs/REPO_MAP.md",
    "change_requests/CR-001-waitlist.md",
    "docs/REQUIREMENTS.md",
    "docs/SPEC.md",
    "docs/ARCHITECTURE.md",
    "docs/factory/CR-001-readiness.md"
  ],
  "recommendation": "PROCEED"
}
```