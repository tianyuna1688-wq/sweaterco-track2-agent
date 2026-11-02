# Track 2 folder — changelog

## v3 — September 2026

Thank you to the teams who flagged these. **Your allocator code does not need to change**:
the allocator signature, `eligible_workshops()`, `orders.csv` and `workshops.csv` are all
exactly as they were, and a normal run (`python simulate.py`, no flags) gives exactly the
numbers it always gave.

### What you need to re-run

| If you have already… | Do this |
|---|---|
| run your system on `dispatch_requests.txt` | Re-run it: 9 of the 30 requests changed (list below) |
| reported `--shock` numbers | Re-run them, and report the average over ten seeds (`--seeds 10`) |
| reported normal-run numbers | Nothing. They are unchanged; `report()` just shows two extra columns |

### 1. The chat inbox: dates fixed (`data/dispatch_requests.txt`)

The inbox is dated 1 April 2026, but many requests asked for orders back by dates in March.
That was a bug in how the inbox was generated, not a puzzle. Nine requests now point at
in-progress orders that are due later in April and that a workshop can actually deliver:

`R04, R06, R07, R16, R17, R22, R23, R26, R27`. The request numbers, senders, times, wording
and the kind of each request are unchanged — only the order, its quantity and its date.
The other 21 requests are exactly as they were.

Three requests are unchanged but are now declared **deliberately impossible**: `R20` (due in 3 days),
`R28` (the order is already overdue) and `R30` (due in 4 days). No workshop can make those
dates. The right behaviour is to say so with the numbers, give the earliest achievable
date, and lay out the options (split, accept lateness, escalate) — not to allocate silently.
`data/data_dictionary.md` now lists how many requests there are of each kind.

### 2. The simulator (`harness/simulate.py`)

- **Assumptions written down** in the header: it is a what-if replay from 2026-01-01 that
  ignores the in-house columns; a workshop takes the whole job as one unit of work; one
  batch goes to one workshop; and the thing it calls is your deterministic allocation
  policy — do not put an LLM call inside the allocator.
- **`--seed N` and `--seeds N`**, plus `average_over_seeds()` for your own allocator. Which
  workshop `--shock` closes depends on the seed, so one seed is one roll of the dice.
- **`--shock` fixed.** A batch already being worked on when the workshop closed used to
  carry on through the closure; it now pauses. And choosing the closed workshop no longer
  shifts the defect draws, so a normal run and a `--shock` run differ only by the closure.
  The closure is day 30 to 44 of the run: 31 January to 14 February 2026.
- **Two extra report columns**: `late days` (mean days late over all batches, on-time ones
  counting as 0) and `% def pcs` (defective batches weighted by size).

### 3. What "beat the baselines" means

The track description now gives the metric and the guardrail for each primary objective,
and replaces "the best ten-line heuristic" with what was meant: a simple rule-based
allocator with no LLM, about the size of the shipped baselines.

### 4. Optional: workshops that only do some stages (`--stages`)

For teams who want a richer model. `python simulate.py --stages` uses two new files,
`data/orders_stages.csv` and `data/workshops_stages.csv` (the originals plus one column
each), and adds a fourth eligibility question: does the workshop cover every stage from the
order's dispatch stage through PACKING? `eligible_workshops()` applies it for you.
**Entirely opt-in** — ignore it and nothing changes. If you use it, say so in your report.
For in-progress orders `dispatch_stage` equals `current_stage` on 1 April, so the stage
files agree with the chat inbox; the simulator reuses the column for its January-to-March
replay (see the note in `data/data_dictionary.md`).

## v2 — September 2026

Comments only: which date `current_queue_days` refers to (1 April for the chat inbox,
1 January as the simulator's starting queue). See the note under `workshops.csv` in
`data/data_dictionary.md`.
