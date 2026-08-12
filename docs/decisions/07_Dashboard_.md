# M7 — Dashboard: Summary & Decisions

## What was built

A Next.js/TypeScript/Tailwind frontend, live against the real backend built
in M2-M6: a home page listing ingested races, a race detail page with an
interactive "timing tower" (lap scrubber + live leaderboard), a results
page (final classification + a per-driver lap-time chart), and a strategy
simulator page wrapping `POST /strategy/simulate` in a real form and
result visualization.

## Key design decisions

**The visual identity is grounded in real motorsport reference material,
not a generic dashboard template.** The color system uses the actual
FIA-regulated tire compound colors (SOFT red, MEDIUM yellow, HARD white,
INTERMEDIATE green, WET blue) as the accent palette, plus the purple F1
broadcasts use to mark a fastest sector/lap. Typography pairs a condensed
display face (Barlow Condensed, styled after motorsport timing graphics)
with a monospace face using tabular figures for lap times and gaps
(JetBrains Mono) — matching how a real timing tower aligns numbers. This
was a deliberate choice to avoid the generic "dark background, one neon
accent" look that's become an AI-generated-dashboard default; every color
and font choice here has a real, checkable source.

**The timing tower recreates a genuine F1 broadcast graphic**, not an
invented UI pattern — position, gap to leader, interval to the car ahead,
and tire compound, in that order, is exactly how a real timing screen
presents it.

**CORS was deliberately deferred from M2 until this milestone actually
needed it** (see ADR-adjacent note in `.env.example` from early in the
project) — a small example of the "don't add infrastructure before it's
load-bearing" principle holding up across the whole project, not just the
backend.

**A backend gap was found and closed while building this, not before.**
There was no endpoint exposing final race classification (finishing
position, status, points) — only lap-by-lap data. `GET
/races/{id}/results` was added specifically because the results page
needed it, which is arguably the right order: the frontend surfaced a real
product gap the backend milestones hadn't needed yet.

## What's next

Phase 8 (M8) — tests, CI/CD, structured logging. The last major gap
between this project and something a FAANG-level interviewer would call
fully "production-shaped."
