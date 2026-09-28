# scripts/

Developer and operational helper scripts (setup, seeding demo data, running
checks). Empty until a script is needed.

Rules:
- Scripts must read credentials from the environment, never from arguments or
  hard-coded values.
- Anything that seeds or resets data must be clearly named as such and must
  refuse to run against a non-local target by default.
