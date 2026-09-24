# src/

Application source code lives here. It is intentionally empty.

Nothing goes in this folder until the team has agreed on the technology stack
(DECISIONS.md, ADR-001) and reviewed the initial architecture (ARCHITECTURE.md).

When code does land here, keep the security boundary visible in the layout:
authorization and permission-aware filtering should be a clearly separated
module that the retrieval and LLM layers depend on, not something spread across
connectors. See SECURITY.md for the invariants that module must uphold.
