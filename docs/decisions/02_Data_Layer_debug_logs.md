# M2 — Data Layer: Debugging Log

Same spirit as the M1 spike's debugging log: a record of what went wrong
and how it was found, kept while the reasoning is still fresh rather than
reconstructed later from memory.

---

### 1. Alembic couldn't find its own scripts folder

**Symptom:** `alembic -c backend/alembic.ini revision --autogenerate ...`
failed immediately with `FAILED: Path doesn't exist: alembic.`

**Root cause:** `alembic.ini`'s `script_location = alembic` is resolved
relative to the _current working directory the command is run from_, not
relative to the location of `alembic.ini` itself. Running the command from
the repo root (required for the `backend.models` import in `env.py` to
resolve) meant Alembic looked for `<repo_root>/alembic/`, not
`<repo_root>/backend/alembic/`.

**Fix:** changed `script_location` to `backend/alembic` (correct relative
to the repo root, which is the fixed convention this project runs Alembic
commands from).

---

### 2. Models crashed on import: `TypeError: unsupported operand type(s) for |`

**Symptom:** the very next `alembic revision --autogenerate` attempt (after
fixing #1) failed while importing `backend/models/models.py`, at the first
`Mapped[str | None]` type hint.

**Root cause:** the modern `X | None` union-type syntax (PEP 604) only
works at runtime on Python 3.10+. The project's venv was still on Python
3.9 (visible in the traceback's file paths), where evaluating `str | None`
outside a string annotation raises a `TypeError` — this isn't optional
tooling behavior, it's a genuine language version gap.

**Fix, short-term:** swapped every `X | None` to `typing.Optional[X]`,
which is 3.9-compatible.
**Fix, actual:** decided this was reason enough to upgrade the project to
Python 3.12 outright (3.9 is already past its official end-of-life) —
rebuilt the venv on 3.12 and reverted the models back to the cleaner
`X | None` syntax, now that it's safely supported.

---

### 3. Weather ingestion would have silently collided with a unique constraint

**Symptom:** caught during code review, before ever running it — not a
runtime failure.

**Root cause:** the first draft of `_load_weather` mapped every raw FastF1
weather reading (roughly one per minute) to an approximate lap number and
inserted one row per reading. But the `weather` table has a unique
constraint on `(race_id, lap_number)`, and a lap typically takes 1–2
minutes — so multiple readings routinely map to the same lap, which would
have raised an integrity error on the second insert for that lap.

**Fix:** rewrote the function to bucket all readings mapping to the same
approximate lap and insert one averaged row per lap, satisfying the
uniqueness constraint by construction rather than by luck.

---

## Takeaway

Two of these three were caught before ever touching production behavior —
#3 by reviewing the code against the schema's own constraints before
running it, and #2's _real_ fix (the Python upgrade) was a deliberate
decision rather than a reactive patch. Worth keeping that habit through
M3+: cross-check new ingestion/simulation code against the constraints
already declared in the schema, not just against "does it run."
