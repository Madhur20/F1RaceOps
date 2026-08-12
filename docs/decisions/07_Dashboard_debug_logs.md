# M7 — Dashboard: Debugging Log

Same format as the M1-M6 logs. This milestone's bugs skew toward
environment/tooling issues rather than algorithmic ones — a natural
consequence of it being the first frontend work in the project.

---

### 1. Backend crashed on startup: `ModuleNotFoundError: No module named 'psycopg2'`

**Symptom:** `uvicorn` failed immediately on import, despite
`psycopg2-binary` being listed in `requirements.txt`.

**Root cause:** the dependency was never actually installed in the
current venv — likely fell out of sync back when the venv was rebuilt
for the Python 3.9 -> 3.12 upgrade earlier in the project.

**Fix:** `pip install -r backend/requirements.txt` against the active
venv. A reminder that a requirements file listing a package is not the
same guarantee as it being installed in the environment actually running.

---

### 2. Frontend crashed: `next.config.json` not supported

**Symptom:** `npm run dev` failed with Next.js explicitly refusing to
load a `.json` config file.

**Root cause:** a stray `next.config.json` existed alongside the correct
`next.config.js` — most likely an artifact of how a downloaded file got
saved locally, not a code bug.

**Fix:** delete the stray file, confirm `next.config.js` has the right
content.

---

### 3. Frontend showed "Couldn't reach the API" despite the backend running

**Symptom:** the backend was confirmed running and reachable via `curl`,
but the Next.js home page's server-side data fetch failed with a generic
`fetch failed` error.

**Root cause:** a `localhost` vs `127.0.0.1` resolution mismatch, common
on macOS with Node's `fetch`. Uvicorn was bound specifically to
`127.0.0.1` (IPv4 only); Node's `fetch` frequently resolves `localhost`
to the IPv6 loopback (`::1`) first, which uvicorn wasn't listening on at
all, producing an immediate connection failure. This is unrelated to
CORS — the failing fetch happens in the home page's server-side render,
inside the Next.js process itself, not in the browser, so CORS doesn't
even apply to it.

**Fix:** pointed the frontend at the explicit IPv4 address
(`NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000` in `.env.local`) instead of
relying on `localhost` resolution.

---

### 4. The "lapped cars, not retirements" note never appeared

**Symptom:** Turkey 2021's final lap correctly shows only 9 of 20 drivers
(the rest were lapped, confirmed via `race_results.status` — a genuine
racing outcome, not a bug; see the investigation that preceded this
fix). A UI note was added to explain this, calibrated from the largest
driver count seen so far in the browsing session — but the note never
showed up when jumping straight to a late lap.

**Root cause:** the lap scrubber debounces rapid changes by 120ms to
avoid hammering the API while dragging. If a user jumped straight to a
late lap (few or no intermediate laps actually fetched), the _first_
completed fetch was already the reduced-count lap — so the session-based
"max drivers seen" baseline was never established from an earlier,
full-field lap before the comparison ran. The note's own logic was
correct; its input data was simply unavailable in this common
navigation path.

**Fix:** stopped relying on session-order to establish field size.
Instead, the race page now does one additional server-side fetch of lap
1's race state (where essentially everyone is still on track) before the
page ever renders, giving a reliable, order-independent field-size
reference regardless of which lap the user looks at first.

---

## Takeaway

Bug #4 is the most instructive one here: a UI feature can be logically
correct and still fail in practice if the data it depends on isn't
reliably available by the time it's needed. The fix wasn't a logic
change — the comparison itself was always right — it was replacing an
opportunistic, order-dependent data source with a deterministic one.
Worth remembering for any future feature that "calibrates as you go":
that pattern is fragile exactly in the common case where a user doesn't
interact with the app in the order the calibration assumes.
