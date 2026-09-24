# scripts/

Developer and operational helper scripts (setup, seeding demo data, running
checks). Intentionally empty until the stack is chosen.

Rules:
- Scripts must read credentials from the environment, never from arguments or
  hard-coded values.
- Anything that seeds or resets data must be clearly named as such and must
  refuse to run against a non-local target by default.
