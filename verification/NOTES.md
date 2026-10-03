# Verification notes — working-capital-optimizer

**Model:** `verification/CashSchedule.lean` (Lean 4.34.1, core library only,
no Mathlib). Check with:

```
~/.elan/bin/lean verification/CashSchedule.lean    # exit 0, no sorry/admit
```

93 theorems. Axiom audit (`#print axioms` on the headline theorems): only
the standard `propext`, `Quot.sound`, `Classical.choice` — no `sorryAx`,
no custom axioms. No source files were modified.

## Scope verdict — read this first

The repo is mostly a Next.js 16 dashboard (shadcn/ui components, API proxy
routes under `src/app/api/wco/`) plus LLM (Gemini) agents. **There is no
capital-constrained payment scheduler anywhere in it** — no knapsack, no
allocation engine, nothing that decides a set of payments against an
available-capital budget. "Scheduling" decisions are made by LLM agents
from computed context; payment amounts are never checked against available
capital by any deterministic code. What *is* deterministic, and is modeled
here:

| Section | Engine | Source |
|---|---|---|
| A | 13-week cash-schedule builder | `wco/agent/src/wco/data/procurement_profitability.py`, `_cash_by_week` ll. 138–148, `_build_cash_inputs` ll. 150–176 |
| B | 13-week forecast skeleton (duplicated Python/Rust) | `wco/agent/src/wco/agents/cashflow_agent.py` ll. 122–151; `wco/agent/rust/src/lib.rs` `cashflow_context` l. 323, skeleton ll. 356–394 |
| C | Agent orchestration topological sort | `wco/agent/src/wco/orchestration/orchestrator.py`, `AGENT_DEPENDENCIES` ll. 30–36, `_topological_sort` ll. 38–88 |
| D | AP early-payment discount rule (duplicated Python/Rust) | `wco/agent/src/wco/agents/ap_agent.py` ll. 86–125; `wco/agent/rust/src/lib.rs` `ap_context` l. 110, rule l. 142 |

The Python agents call the Rust binary first (`wco/agent/src/wco/rust_core.py`);
if it is missing they fall back to the Python implementations — which is why
B and D each exist twice, and why the duplicates can (and do) diverge.

Modeling choices: A is modeled in integer cents (the Python code rounds
every intermediate to 2dp, which is the identity on cent-exact values);
B over `Rat` with the code's decimal constants as exact rationals
(4.33 = 433/100, 1.02 = 102/100, factors 0.92/0.97); D in basis points with
the float comparison cross-multiplied into exact `Nat` arithmetic (valid
for 0 ≤ disc < 100%; see finding D-3).

## Theorem → source mapping

### Section A — schedule builder (`procurement_profitability.py`)

Validation `_cash_by_week` ll. 138–148 (week must be an integer 1–13,
l. 142–143; duplicates rejected, l. 145) is the model's `ValidRows`
hypothesis. `_build_cash_inputs` ll. 150–176: exactly 13 entries
(`range(1, 14)`, l. 155); missing weeks get zero flows (ll. 157–159);
`net_change = round(inflows − outflows)` (l. 164);
`closing = round(opening + net_change)` (l. 165).

| Theorem | Claim |
|---|---|
| `build_length`, `build_weeks` | Output has exactly 13 entries, weeks 1–13 in order |
| `build_week_window` | Every scheduled entry lies in the 1–13 window |
| `findRow_eq_of_mem_nodup`, `build_row_slot` | With duplicate-free weeks, each input row lands in exactly its own week slot (scheduled at most once — and exactly once) |
| `fieldAt_eq_zero_of_not_mem` | Missing weeks contribute zero (ll. 157–159) |
| `fieldAt_sum_eq`, `build_inflows_sum`, `build_outflows_sum` | Conservation of totals: sum over the window of scheduled inflows (resp. outflows) = sum over input rows — nothing lost, nothing double-counted |
| `sched_accounting`, `sched_telescope` | Per-week `closing = opening + inflows − outflows`; final balance telescopes to initial + Σ inflows − Σ outflows |
| `build_conservation` | For the concrete builder: final balance = total inflows − total outflows — **only under the hypothesis that no row supplies `opening_balance`** (see A-2) |
| `sched_adjacent`, `build_first_two_chain` | Adjacent entries chain (`opening(w+1) = closing(w)`) under the same no-override hypothesis |
| `overdraft_example`, `closing_below_any_bound` | **Counterexamples:** no balance floor exists (see A-1) |
| `override_breaks_chain_example` | **Counterexample:** an `opening_balance` override silently breaks the chain (see A-2) |

### Section B — forecast skeleton (`cashflow_agent.py` / Rust `cashflow_context`)

Weekly collections = `monthly_revenue / 4.33` (l. 123; Rust l. 356),
payments = `monthly_cogs / 4.33` (l. 124; Rust l. 357); collection factor
0.92 (weeks ≤ 4) / 0.97 (≤ 8) / 1.0 (l. 131; Rust ll. 368–370); outflows =
payments × 1.02 (l. 133; Rust l. 375); balance threaded through one
variable (l. 135); `risk_weeks` = weeks closing below `min_cash_threshold`
(default 500 000, l. 148; Rust l. 389).

| Theorem | Claim |
|---|---|
| `fcEntry_opening`, `fcEntry_closing`, `fc_chain` | Emitted entries chain by construction: next opening = previous closing |
| `fcClosing_eq_sum` | Telescope: closing after week n = opening + Σ weekly nets |
| `mem_fcRiskWeeks` | `i ∈ risk_weeks ↔ 1 ≤ i ≤ 13 ∧ closing(i) < threshold` |
| `fcFactor_lo/mid/hi`, `fcFactor_le_one`, `fcFactor_nonneg` | Factor bands are exactly 0.92/0.97/1.0 and lie in [0, 1] |
| `fcCollections_le` | Collections never exceed un-factored weekly revenue (non-negative revenue) |
| `fcPayments_nonneg`, `fcOutflows_nonneg`, `fcNet_le_collections` | Outflows are non-negative (non-negative COGS) and only subtract: weekly net ≤ weekly collections |

### Section C — topological sort (`orchestrator.py`)

`AGENT_DEPENDENCIES` ll. 30–36: AR/AP/INVENTORY are sources, CASHFLOW
depends on all three. The model uses a first-ready scan; the code uses a
FIFO Kahn queue — tie-breaking can differ, but the three properties below
are scan-independent, and for the fixed graph the concrete output
coincides (`topoSort_real`).

| Theorem | Claim |
|---|---|
| `schedule_perm` | A successful run schedules each agent exactly once (output is a permutation of the input) |
| `schedule_ordered` | In a successful run, every dependency of every agent is done or appears strictly before it |
| `schedule_complete`, `exists_ready` | A closed (deps stay within done ∪ pending) and stratified (acyclic, witnessed by `rankOn`) pending list always schedules in full |
| `edgesOn_real`, `stratOn_real` | The real graph is closed and stratified |
| `topoSort_real` | The real graph schedules to `[AR, AP, INV, CF]` (by computation) |
| `topoSort_real_complete` | …and that run is complete, duplicate-free, and dependency-ordered |
| `topoSort_cycle_none`, `fallback_cycle`, `fallback_cycle_violates` | **Counterexamples:** on a cycle the honest scheduler fails, but the code's fallback emits an order that violates dependencies (see C-1) |
| `knownDeps_drops_unknown` | Dependencies on unregistered capabilities vanish silently (see C-2) |
| `capability_collapse` | Duplicate capabilities silently drop an agent (see C-3) |

### Section D — discount rule (`ap_agent.py` / Rust `ap_context`)

`extra_days = max((due − discount_deadline).days, 1)` (l. 104);
`annualised = (disc/(1−disc)) × (365/extra_days)` (l. 105);
TAKE iff `annualised > cost_of_capital`, else SKIP (ll. 106, 113);
REVIEW on date-parse failure (ll. 117–123, Python only).

| Theorem | Claim |
|---|---|
| `decideOn_take_iff`, `decideOn_skip_iff` | Soundness + completeness of the rule in cross-multiplied form: TAKE ↔ `cap·(10000−disc)·extra < disc·365·10000` (basis points) |
| `extraDays_ge_one`, `extraDays_of_gt` | The day-count floor: `extra_days ≥ 1`, and equals the raw difference when positive |
| `decideOn_zero_disc` | A 0% discount is never taken |
| `decideOn_zero_cap` | At zero cost of capital, every positive discount is taken |
| `default_divergence` | **Counterexample:** Python and Rust defaults decide the same invoice oppositely (see D-1) |
| `decideOn_full_discount` | At disc = 100% the cross-multiplied rule degenerates to always-TAKE while the code divides by zero (see D-3) |
| `decideOpt_review_left/right`, `decideOpt_some` | Missing/unparseable dates → REVIEW; present dates → the TAKE/SKIP rule |

## Discrepancies and risks

**A-1. There is no capital constraint at all (headline).** `_build_cash_inputs`
never compares any balance to a floor, a budget, or available capital, and
takes no such parameter. `closing_below_any_bound` proves the emitted
schedule's closing balance is *unbounded below*: e.g. opening 100, week-1
outflows 500 ⇒ closing **−400**, schedule still produced in full
(`overdraft_example`). The task brief's invariant "scheduled payments never
exceed available capital in aggregate" is not merely unproven in this
codebase — there is no capital input for it to be stated against. The same
holds downstream: the AP agent *recommends* early payments (Section D) but
nothing aggregates those recommendations against the cash position.

**A-2. `opening_balance` overrides break the balance chain.**
`_build_cash_inputs` l. 161: `opening = _number(row, "opening_balance",
balance)` — a row that supplies `opening_balance` *replaces* the running
balance instead of being checked against it. `override_breaks_chain_example`:
week 1 closes at 10500, week 2 supplies `opening_balance = 999`, and the
emitted schedule uses 999 — the running balance is silently discarded, so
`closing(w) = opening(w+1)` fails and the findings line "13-week net cash
change is Σ net_change" (l. 76) no longer reconciles with
final − initial balance. `build_conservation` therefore needs the
no-override hypothesis. (The repo's own test fixture passes only because
its hand-supplied openings happen to agree with the chain.)

**A-3. Validation is the only guard, and it lives outside the builder.**
Duplicate weeks and out-of-window weeks are rejected in `_cash_by_week`
(ll. 142–145), but `_build_cash_inputs` itself trusts its dict argument;
the model's `ValidRows` hypothesis mirrors the validation step, and
`findRow` semantics show why it matters: lookup takes the *first* matching
row, so a bypassed validation would silently shadow later duplicates.

**B-1. Forecast asymmetry (in the code, faithfully modeled).** Collections
are haircut by the 0.92/0.97 factor but payments are not, then payments are
marked *up* 2% — the skeleton is conservative in both directions. No bug,
but worth knowing the "forecast" is a fixed stencil, not data-driven:
amounts are constant across all 13 weeks by construction.

**C-1. Cycle fallback violates dependency order.** If Kahn's queue stalls,
`_topological_sort` logs a warning (l. 85) and appends the remaining agents
in original order (l. 86). `fallback_cycle_violates` proves the emitted
order can put an agent *before* its own dependency (AP after AR, though AR
depends on AP) — downstream agents then run without their inputs, silently
apart from the log line.

**C-2. Dependencies on missing agents are silently dropped.** L. 65:
`present_deps = deps & set(capability_to_agent.keys())`. If the inventory
agent is absent, CASHFLOW's dependency on it simply disappears
(`knownDeps_drops_unknown`) and cashflow runs without inventory data.

**C-3. Duplicate capabilities collapse.** `capability_to_agent` is a dict
comprehension (ll. 54–56): the last agent advertising a capability wins,
and earlier ones never run (`capability_collapse`) — no error, no warning.

**D-1. Python/Rust default divergence (machine-checked).** Python defaults
`cost_of_capital` to **0.08** (`ap_agent.py` l. 89); the Rust core reads it
via `num()`, which defaults any missing field to **0.0** (`lib.rs` l. 6,
used at l. 113). At cap = 0 every positive discount clears the hurdle
(`decideOn_zero_cap`), so the same invoice — 0.5% discount, 30 extra days —
is **SKIP under the Python default and TAKE under the Rust default**
(`default_divergence`). Which answer the user sees depends on whether the
Rust binary happened to build. Related smaller divergence: Rust reports
`discountable_invoices_count = discount_analysis.len()` (l. 176), while
Python's corresponding count is over all discount-available invoices
(ll. 86–88) whether or not their dates parsed.

**D-2. REVIEW exists only in Python.** Unparseable dates produce a REVIEW
recommendation in the Python fallback (ll. 117–123); the Rust `ap_context`
has only TAKE/SKIP (l. 142) — a parse failure there is invisible (the
invoice drops out of the analysis, which also feeds D-1's count).

**D-3. The discount formula is singular at disc = 100%.** L. 105 divides by
`1 − disc_pct`; at `discount_pct = 100` that is a float division by zero.
The cross-multiplied model stays total and degenerates to always-TAKE
(`decideOn_full_discount`), so model and code agree *nowhere* at the
boundary — data must keep discounts < 100%, and nothing in either
implementation validates that.

## Modeling caveats

- Floats: the code computes in binary floats with `round(·, 2)` at each
  step (Python uses round-half-even on the decimal representation). The
  cent/`Rat` models are exact; on cent-exact inputs they coincide with the
  code. Non-cent inputs can drift by at most a half-cent per rounding step
  in the code — the model does not track that drift.
- Section C's scan order (first-ready) vs the code's FIFO queue: all
  proved properties are scan-independent; only un-proved tie-break order
  could differ, and for the fixed graph the outputs coincide
  (`topoSort_real`).
- Section D's equivalence between the float comparison and the
  cross-multiplied `Nat` comparison holds for 0 ≤ disc < 100% and
  extra ≥ 1 (all factors positive); it is argued here and in the Lean
  docstring, and the boundary case is exhibited separately (D-3).
