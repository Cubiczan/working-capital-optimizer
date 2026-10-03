/-
  CashSchedule.lean — Lean 4 (core library only) formal model of the
  deterministic scheduling core of the working-capital-optimizer repo.

  The repo is mostly a Next.js dashboard plus LLM agents.  The only
  deterministic engines that "schedule" anything are:

  * Section A — `_build_cash_inputs` / `_cash_by_week` in
    `wco/agent/src/wco/data/procurement_profitability.py` (ll. 138–176):
    validated weekly cash rows are placed into a fixed 13-week window and
    a running balance is threaded through them.  Modelled in integer
    cents (the Python code rounds every intermediate to 2dp, which is
    the identity on cent-exact values).

  * Section B — the flat 13-week forecast skeleton duplicated in
    `wco/agent/src/wco/agents/cashflow_agent.py` (ll. 122–151) and
    `wco/agent/rust/src/lib.rs` `cashflow_context` (ll. 356–394):
    constant weekly collections/payments with a week-band collection
    factor, balance chained by construction.  Modelled over `Rat`.

  * Section C — `_topological_sort` in
    `wco/agent/src/wco/orchestration/orchestrator.py` (ll. 38–88):
    Kahn's algorithm over the fixed dependency graph
    (CASHFLOW depends on AR, AP, INVENTORY).

  * Section D — the early-payment discount TAKE/SKIP rule duplicated in
    `wco/agent/src/wco/agents/ap_agent.py` (ll. 86–125) and
    `wco/agent/rust/src/lib.rs` `ap_context` (ll. 110–176), modelled in
    cross-multiplied integer form (basis points).

  See NOTES.md for the theorem → source mapping and the discrepancy /
  risk notes (in particular: there is NO capital-constrained payment
  scheduler anywhere in the repo — Section A proves the schedule
  builder enforces no balance floor at all).
-/

namespace WCO

/-! ## Generic list-sum helpers -/

theorem sum_map_congr {g h : Nat → Int} {ws : List Nat}
    (H : ∀ w ∈ ws, g w = h w) : (ws.map g).sum = (ws.map h).sum := by
  induction ws with
  | nil => rfl
  | cons w ws ih =>
    have hw : g w = h w := H w (by simp)
    have ih' := ih (fun x hx => H x (List.mem_cons_of_mem w hx))
    simp [List.map_cons, List.sum_cons, hw, ih']

theorem sum_map_add {a b : Nat → Int} {ws : List Nat} :
    (ws.map (fun w => a w + b w)).sum = (ws.map a).sum + (ws.map b).sum := by
  induction ws with
  | nil => rfl
  | cons w ws ih =>
    simp only [List.map_cons, List.sum_cons, ih]
    omega

theorem sum_map_sub {a b : Nat → Int} {ws : List Nat} :
    (ws.map (fun w => a w - b w)).sum = (ws.map a).sum - (ws.map b).sum := by
  induction ws with
  | nil => rfl
  | cons w ws ih =>
    simp only [List.map_cons, List.sum_cons, ih]
    omega

theorem sum_eq_zero_of_forall {g : Nat → Int} {ws : List Nat}
    (H : ∀ w ∈ ws, g w = 0) : (ws.map g).sum = 0 := by
  induction ws with
  | nil => rfl
  | cons w ws ih =>
    have hw : g w = 0 := H w (by simp)
    have ih' := ih (fun x hx => H x (List.mem_cons_of_mem w hx))
    simp [List.map_cons, List.sum_cons, hw, ih']

/-- Splitting one distinguished week out of a sum over a duplicate-free
    week list: the indicator function contributes exactly once. -/
theorem sum_indicator {ws : List Nat} {x : Nat} {v : Int}
    (hnd : ws.Nodup) (hx : x ∈ ws) :
    (ws.map (fun w => if w = x then v else 0)).sum = v := by
  induction ws with
  | nil => simp at hx
  | cons a ws ih =>
    rw [List.nodup_cons] at hnd
    rcases List.mem_cons.mp hx with (rfl | hx')
    · have hzero : ∀ w ∈ ws, (if w = x then v else 0) = 0 := by
        intro w hw
        have hne : w ≠ x := fun h => hnd.1 (h ▸ hw)
        rw [if_neg hne]
      have hsum := sum_eq_zero_of_forall hzero
      simp [List.map_cons, List.sum_cons, hsum]
    · have hne : a ≠ x := fun h => hnd.1 (h ▸ hx')
      have ih' := ih hnd.2 hx'
      simp [List.map_cons, List.sum_cons, ih', if_neg hne]

/-! ## Section A — the 13-week cash schedule builder

Model of `_cash_by_week` (validation: weeks are integers in [1,13],
duplicates rejected) and `_build_cash_inputs` (13 slots, missing weeks
are zero-flow, a row's `opening_balance` overrides the running balance).
-/

/-- A normalized weekly cash row (`procurement_profitability.py`:
    `week`, optional `opening_balance`, `inflows`, `outflows`). -/
structure CashRow where
  week : Nat
  opening : Option Int
  inflows : Int
  outflows : Int
deriving DecidableEq, Repr

/-- First row for a week — the lookup `_cash_by_week` builds a dict with
    (duplicates are rejected before this is ever used on them). -/
def findRow : List CashRow → Nat → Option CashRow
  | [], _ => none
  | r :: rs, w => if r.week = w then some r else findRow rs w

theorem findRow_eq_none_iff {rows : List CashRow} {w : Nat} :
    findRow rows w = none ↔ ∀ r ∈ rows, r.week ≠ w := by
  induction rows with
  | nil => simp [findRow]
  | cons r rs ih =>
    constructor
    · intro h r' hr'
      by_cases hw : r.week = w
      · simp [findRow, hw] at h
      · have hne : findRow rs w = none := by
          have := h
          simp [findRow, hw] at this
          exact this
        rcases List.mem_cons.mp hr' with (rfl | hr'')
        · exact hw
        · exact ih.mp hne r' hr''
    · intro h
      have hw : r.week ≠ w := h r (by simp)
      have hne : findRow rs w = none :=
        ih.mpr (fun r' hr' => h r' (List.mem_cons_of_mem r hr'))
      simp [findRow, hw, hne]

theorem findRow_mem {rows : List CashRow} {w : Nat} {r : CashRow}
    (h : findRow rows w = some r) : r ∈ rows := by
  induction rows with
  | nil => simp [findRow] at h
  | cons a rs ih =>
    by_cases hw : a.week = w
    · simp [findRow, hw] at h
      rw [← h]
      exact List.mem_cons_self
    · simp [findRow, hw] at h
      exact List.mem_cons_of_mem a (ih h)

/-- With duplicate-free weeks, lookup finds the unique row for its week. -/
theorem findRow_eq_of_mem_nodup {rows : List CashRow} {r : CashRow}
    (hnd : (rows.map CashRow.week).Nodup) (hr : r ∈ rows) :
    findRow rows r.week = some r := by
  induction rows with
  | nil => simp at hr
  | cons a rs ih =>
    rw [List.map_cons, List.nodup_cons] at hnd
    rcases List.mem_cons.mp hr with (rfl | hr')
    · simp [findRow]
    · have haw : a.week ≠ r.week := by
        intro h
        apply hnd.1
        rw [h]
        exact List.mem_map.mpr ⟨r, hr', rfl⟩
      have ih' := ih hnd.2 hr'
      simp [findRow, haw, ih']

/-- The field of the row scheduled in week `w`, or 0 if there is none
    (missing weeks contribute zero flow — `_build_cash_inputs`). -/
def fieldAt (rows : List CashRow) (g : CashRow → Int) (w : Nat) : Int :=
  match findRow rows w with
  | some r => g r
  | none => 0

theorem fieldAt_cons {r : CashRow} {rs : List CashRow} {g : CashRow → Int} {w : Nat} :
    fieldAt (r :: rs) g w = if r.week = w then g r else fieldAt rs g w := by
  by_cases h : r.week = w <;> simp [fieldAt, findRow, h]

theorem fieldAt_eq_zero_of_not_mem {rows : List CashRow} {g : CashRow → Int} {w : Nat}
    (H : ∀ r ∈ rows, r.week ≠ w) : fieldAt rows g w = 0 := by
  have h : findRow rows w = none := findRow_eq_none_iff.mpr H
  simp [fieldAt, h]

theorem fieldAt_eq_of_mem_nodup {rows : List CashRow} {r : CashRow} {g : CashRow → Int}
    (hnd : (rows.map CashRow.week).Nodup) (hr : r ∈ rows) :
    fieldAt rows g r.week = g r := by
  simp [fieldAt, findRow_eq_of_mem_nodup hnd hr]

/-- One emitted week of the schedule (`cash_inputs` entry). -/
structure Entry where
  week : Nat
  opening : Int
  inflows : Int
  outflows : Int
  netChange : Int
  closing : Int
deriving DecidableEq, Repr

/-- The balance-threading loop of `_build_cash_inputs`, generalized over
    how a week's opening and flows are determined.  The next week's
    running balance is this week's closing. -/
def sched (openAt : Nat → Int → Int) (flow : Nat → Int × Int) :
    List Nat → Int → List Entry
  | [], _ => []
  | w :: ws, bal =>
    { week := w, opening := openAt w bal, inflows := (flow w).1,
      outflows := (flow w).2, netChange := (flow w).1 - (flow w).2,
      closing := openAt w bal + ((flow w).1 - (flow w).2) }
      :: sched openAt flow ws (openAt w bal + ((flow w).1 - (flow w).2))

theorem sched_weeks (o : Nat → Int → Int) (f : Nat → Int × Int)
    {ws : List Nat} {bal : Int} :
    (sched o f ws bal).map Entry.week = ws := by
  induction ws generalizing bal with
  | nil => rfl
  | cons w ws ih => simp [sched, ih]

theorem sched_length (o : Nat → Int → Int) (f : Nat → Int × Int)
    {ws : List Nat} {bal : Int} :
    (sched o f ws bal).length = ws.length := by
  have h := sched_weeks o f (ws := ws) (bal := bal)
  have h2 := congrArg List.length h
  rwa [List.length_map] at h2

theorem sched_accounting (o : Nat → Int → Int) (f : Nat → Int × Int)
    {ws : List Nat} {bal : Int} {e : Entry} (he : e ∈ sched o f ws bal) :
    e.closing = e.opening + e.netChange ∧ e.netChange = e.inflows - e.outflows := by
  induction ws generalizing bal with
  | nil => simp [sched] at he
  | cons w ws ih =>
    simp only [sched, List.mem_cons] at he
    rcases he with (rfl | he')
    · exact ⟨rfl, rfl⟩
    · exact ih he'

theorem sched_inflows_sum (o : Nat → Int → Int) (f : Nat → Int × Int)
    {ws : List Nat} {bal : Int} :
    ((sched o f ws bal).map Entry.inflows).sum
      = (ws.map (fun w => (f w).1)).sum := by
  induction ws generalizing bal with
  | nil => rfl
  | cons w ws ih => simp [sched, List.map_cons, List.sum_cons, ih]

theorem sched_outflows_sum (o : Nat → Int → Int) (f : Nat → Int × Int)
    {ws : List Nat} {bal : Int} :
    ((sched o f ws bal).map Entry.outflows).sum
      = (ws.map (fun w => (f w).2)).sum := by
  induction ws generalizing bal with
  | nil => rfl
  | cons w ws ih => simp [sched, List.map_cons, List.sum_cons, ih]

theorem sched_net_sum (o : Nat → Int → Int) (f : Nat → Int × Int)
    {ws : List Nat} {bal : Int} :
    ((sched o f ws bal).map Entry.netChange).sum
      = (ws.map (fun w => (f w).1 - (f w).2)).sum := by
  induction ws generalizing bal with
  | nil => rfl
  | cons w ws ih => simp [sched, List.map_cons, List.sum_cons, ih]

/-- If every week's opening is the running balance (no overrides), the
    schedule is a clean chain: the final balance is the initial balance
    plus the sum of all net changes (telescoping conservation). -/
theorem sched_telescope (o : Nat → Int → Int) (f : Nat → Int × Int)
    (H : ∀ w b, o w b = b) {ws : List Nat} {bal : Int} :
    (sched o f ws bal).foldl (fun _ e => e.closing) bal
      = bal + ((sched o f ws bal).map Entry.netChange).sum := by
  induction ws generalizing bal with
  | nil => simp [sched]
  | cons w ws ih =>
    have hopen : o w bal = bal := H w bal
    simp only [sched, hopen, List.foldl_cons, List.map_cons, List.sum_cons]
    rw [ih]
    omega

theorem sched_head_opening (o : Nat → Int → Int) (f : Nat → Int × Int)
    {w : Nat} {ws : List Nat} {bal : Int} :
    ((sched o f (w :: ws) bal).head?).map Entry.opening = some (o w bal) := rfl

theorem sched_tail (o : Nat → Int → Int) (f : Nat → Int × Int)
    {w : Nat} {ws : List Nat} {bal : Int} :
    (sched o f (w :: ws) bal).tail
      = sched o f ws (o w bal + ((f w).1 - (f w).2)) := rfl

/-- Adjacent entries chain (next opening = previous closing) whenever
    openings always come from the running balance. -/
theorem sched_adjacent (o : Nat → Int → Int) (f : Nat → Int × Int)
    (H : ∀ w b, o w b = b) {w₁ w₂ : Nat} {ws : List Nat} {bal : Int}
    {e₁ e₂ : Entry} {rest : List Entry}
    (h : sched o f (w₁ :: w₂ :: ws) bal = e₁ :: e₂ :: rest) :
    e₂.opening = e₁.closing := by
  have htail : sched o f (w₂ :: ws) (o w₁ bal + ((f w₁).1 - (f w₁).2))
      = e₂ :: rest := by
    have := congrArg List.tail h
    rwa [sched_tail] at this
  have hhead : ((sched o f (w₂ :: ws) (o w₁ bal + ((f w₁).1 - (f w₁).2))).head?).map
      Entry.opening = some (o w₂ (o w₁ bal + ((f w₁).1 - (f w₁).2))) :=
    sched_head_opening o f
  rw [htail] at hhead
  simp at hhead
  have hclose : e₁.closing = o w₁ bal + ((f w₁).1 - (f w₁).2) := by
    have h1 : (sched o f (w₁ :: w₂ :: ws) bal).head? = some e₁ := by rw [h]; rfl
    have h2 : ((sched o f (w₁ :: w₂ :: ws) bal).head?).map Entry.closing
        = some (o w₁ bal + ((f w₁).1 - (f w₁).2)) := rfl
    rw [h1] at h2
    simp at h2
    exact h2
  rw [← hclose] at hhead
  rw [H] at hhead
  exact hhead

/-! ## Section A (continued) — the concrete builder -/

/-- `_build_cash_inputs` opening rule: a row's `opening_balance` when
    present, otherwise the running balance; missing week → running
    balance. -/
def adaptOpen (rows : List CashRow) (w : Nat) (bal : Int) : Int :=
  match findRow rows w with
  | some r => r.opening.getD bal
  | none => bal

/-- `_build_cash_inputs` flow rule: the row's flows, or zero for a
    missing week. -/
def adaptFlow (rows : List CashRow) (w : Nat) : Int × Int :=
  match findRow rows w with
  | some r => (r.inflows, r.outflows)
  | none => (0, 0)

/-- `adapt_normalized_records`' cash schedule: weeks 1..13, starting
    balance 0 (`_build_cash_inputs` initialises `balance = 0.0`). -/
def build (rows : List CashRow) : List Entry :=
  sched (adaptOpen rows) (adaptFlow rows) (List.range' 1 13) 0

theorem adaptFlow_fst (rows : List CashRow) (w : Nat) :
    (adaptFlow rows w).1 = fieldAt rows CashRow.inflows w := by
  cases h : findRow rows w <;> simp [adaptFlow, fieldAt, h]

theorem adaptFlow_snd (rows : List CashRow) (w : Nat) :
    (adaptFlow rows w).2 = fieldAt rows CashRow.outflows w := by
  cases h : findRow rows w <;> simp [adaptFlow, fieldAt, h]

/-- The validation `_cash_by_week` + `_number` perform: every week in
    the 1..13 window, no duplicate weeks. -/
def ValidRows (rows : List CashRow) : Prop :=
  (∀ r ∈ rows, 1 ≤ r.week ∧ r.week ≤ 13) ∧ (rows.map CashRow.week).Nodup

theorem build_length (rows : List CashRow) : (build rows).length = 13 := by
  have h := sched_length (adaptOpen rows) (adaptFlow rows)
    (ws := List.range' 1 13) (bal := 0)
  rwa [List.length_range'] at h

theorem build_weeks (rows : List CashRow) :
    (build rows).map Entry.week = List.range' 1 13 :=
  sched_weeks _ _

/-- Window constraint: every scheduled entry lies in weeks 1..13. -/
theorem build_week_window {rows : List CashRow} {e : Entry}
    (he : e ∈ build rows) : 1 ≤ e.week ∧ e.week ≤ 13 := by
  have hmem : e.week ∈ (build rows).map Entry.week :=
    List.mem_map.mpr ⟨e, he, rfl⟩
  rw [build_weeks] at hmem
  rw [List.mem_range'] at hmem
  obtain ⟨i, hi, hwi⟩ := hmem
  omega

/-- Each valid row is scheduled in exactly its own week slot: with
    duplicate-free weeks the slot values are the row's own flows. -/
theorem build_row_slot {rows : List CashRow} {r : CashRow}
    (hnd : (rows.map CashRow.week).Nodup) (hr : r ∈ rows) :
    fieldAt rows CashRow.inflows r.week = r.inflows
      ∧ fieldAt rows CashRow.outflows r.week = r.outflows :=
  ⟨fieldAt_eq_of_mem_nodup hnd hr, fieldAt_eq_of_mem_nodup hnd hr⟩

/-- Sum over the whole 13-week window of the per-week slot values equals
    the sum over the input rows — every obligation is counted exactly
    once (conservation of totals).  Induction on the row list, splitting
    one week's contribution out of the window sum at each step. -/
theorem fieldAt_sum_eq (rows : List CashRow) (g : CashRow → Int)
    (hb : ∀ r ∈ rows, 1 ≤ r.week ∧ r.week ≤ 13)
    (hnd : (rows.map CashRow.week).Nodup) :
    ((List.range' 1 13).map (fieldAt rows g)).sum = (rows.map g).sum := by
  induction rows with
  | nil => exact sum_eq_zero_of_forall (fun w _ => rfl)
  | cons r rs ih =>
    have hb_r := hb r (by simp)
    have hb_rs : ∀ x ∈ rs, 1 ≤ x.week ∧ x.week ≤ 13 :=
      fun x hx => hb x (List.mem_cons_of_mem r hx)
    rw [List.map_cons, List.nodup_cons] at hnd
    have ih' := ih hb_rs hnd.2
    have hpoint : ∀ w ∈ List.range' 1 13,
        fieldAt (r :: rs) g w
          = fieldAt rs g w + (if w = r.week then g r else 0) := by
      intro w _
      by_cases h : w = r.week
      · subst h
        have hzero : fieldAt rs g r.week = 0 := by
          apply fieldAt_eq_zero_of_not_mem
          intro r' hr' hcon
          apply hnd.1
          rw [← hcon]
          exact List.mem_map.mpr ⟨r', hr', rfl⟩
        rw [fieldAt_cons]
        simp [hzero]
      · have hne : r.week ≠ w := fun hcon => h hcon.symm
        rw [fieldAt_cons, if_neg hne, if_neg h]
        omega
    calc ((List.range' 1 13).map (fieldAt (r :: rs) g)).sum
        = ((List.range' 1 13).map
            (fun w => fieldAt rs g w + (if w = r.week then g r else 0))).sum :=
          sum_map_congr hpoint
      _ = ((List.range' 1 13).map (fieldAt rs g)).sum
            + ((List.range' 1 13).map
                (fun w => if w = r.week then g r else 0)).sum :=
          sum_map_add
      _ = (rs.map g).sum + g r := by
          rw [ih', sum_indicator (by decide) (by
            rw [List.mem_range']
            exact ⟨r.week - 1, by omega, by omega⟩)]
      _ = ((r :: rs).map g).sum := by
          rw [List.map_cons, List.sum_cons]
          omega

theorem build_inflows_sum {rows : List CashRow} (hv : ValidRows rows) :
    ((build rows).map Entry.inflows).sum = (rows.map CashRow.inflows).sum := by
  have h1 := sched_inflows_sum (adaptOpen rows) (adaptFlow rows)
    (ws := List.range' 1 13) (bal := 0)
  have h2 : ((List.range' 1 13).map (fun w => (adaptFlow rows w).1)).sum
      = ((List.range' 1 13).map (fieldAt rows CashRow.inflows)).sum :=
    sum_map_congr (fun w _ => adaptFlow_fst rows w)
  have h3 := fieldAt_sum_eq rows CashRow.inflows hv.1 hv.2
  exact h1.trans (h2.trans h3)

theorem build_outflows_sum {rows : List CashRow} (hv : ValidRows rows) :
    ((build rows).map Entry.outflows).sum = (rows.map CashRow.outflows).sum := by
  have h1 := sched_outflows_sum (adaptOpen rows) (adaptFlow rows)
    (ws := List.range' 1 13) (bal := 0)
  have h2 : ((List.range' 1 13).map (fun w => (adaptFlow rows w).2)).sum
      = ((List.range' 1 13).map (fieldAt rows CashRow.outflows)).sum :=
    sum_map_congr (fun w _ => adaptFlow_snd rows w)
  have h3 := fieldAt_sum_eq rows CashRow.outflows hv.1 hv.2
  exact h1.trans (h2.trans h3)

/-- When no row overrides its opening balance, the adapter's opening
    rule always yields the running balance (the chain hypothesis). -/
theorem adaptOpen_chained {rows : List CashRow}
    (hno : ∀ r ∈ rows, r.opening = none) :
    ∀ w b, adaptOpen rows w b = b := by
  intro w b
  cases h : findRow rows w with
  | none => simp [adaptOpen, h]
  | some r =>
    have hr : r ∈ rows := findRow_mem h
    simp [adaptOpen, h, hno r hr]

/-- Conservation for the adapter: with no opening overrides, the final
    balance equals total inflows minus total outflows — scheduled and
    unscheduled obligations reconcile exactly. -/
theorem build_conservation {rows : List CashRow} (hv : ValidRows rows)
    (hno : ∀ r ∈ rows, r.opening = none) :
    (build rows).foldl (fun _ e => e.closing) 0
      = (rows.map CashRow.inflows).sum - (rows.map CashRow.outflows).sum := by
  have htel := sched_telescope (adaptOpen rows) (adaptFlow rows)
    (adaptOpen_chained hno) (ws := List.range' 1 13) (bal := 0)
  have hnet : ((build rows).map Entry.netChange).sum
      = (rows.map CashRow.inflows).sum - (rows.map CashRow.outflows).sum := by
    have h1 := sched_net_sum (adaptOpen rows) (adaptFlow rows)
      (ws := List.range' 1 13) (bal := 0)
    have h2 : ((List.range' 1 13).map
          (fun w => (adaptFlow rows w).1 - (adaptFlow rows w).2)).sum
        = ((List.range' 1 13).map
            (fun w => fieldAt rows CashRow.inflows w
              - fieldAt rows CashRow.outflows w)).sum :=
      sum_map_congr (fun w _ => by rw [adaptFlow_fst, adaptFlow_snd])
    have h3 : ((List.range' 1 13).map
          (fun w => fieldAt rows CashRow.inflows w
            - fieldAt rows CashRow.outflows w)).sum
        = ((List.range' 1 13).map (fieldAt rows CashRow.inflows)).sum
          - ((List.range' 1 13).map (fieldAt rows CashRow.outflows)).sum :=
      sum_map_sub
    have h4 := fieldAt_sum_eq rows CashRow.inflows hv.1 hv.2
    have h5 := fieldAt_sum_eq rows CashRow.outflows hv.1 hv.2
    exact h1.trans (h2.trans (h3.trans (by rw [h4, h5])))
  have htel' : (build rows).foldl (fun _ e => e.closing) 0
      = 0 + ((build rows).map Entry.netChange).sum := htel
  rw [htel', hnet, Int.zero_add]

/-- The first two entries of a real build chain correctly when no row
    overrides its opening (`List.range' 1 13` is definitionally
    `1 :: 2 :: List.range' 3 11`). -/
theorem build_first_two_chain {rows : List CashRow}
    (hno : ∀ r ∈ rows, r.opening = none)
    {e₁ e₂ : Entry} {rest : List Entry}
    (h : build rows = e₁ :: e₂ :: rest) : e₂.opening = e₁.closing := by
  have h' : sched (adaptOpen rows) (adaptFlow rows)
      (1 :: 2 :: List.range' 3 11) 0 = e₁ :: e₂ :: rest := h
  exact sched_adjacent _ _ (adaptOpen_chained hno) h'

/-! ## Counterexamples — what the builder does NOT enforce -/

/-- **No capital floor.**  A single week whose outflows exceed the
    available cash produces a negative closing balance and the schedule
    is still produced in full (13 entries).  `_build_cash_inputs` has
    no balance check of any kind; nor does `adapt_normalized_records`
    take a minimum-balance parameter. -/
theorem overdraft_example :
    ((build [{ week := 1, opening := some 100, inflows := 0,
               outflows := 500 }]).head?).map Entry.closing
      = some (-400) := by decide

/-- Stronger: closings are unbounded below — for every bound there is
    a valid input whose schedule closes beneath it.  (Negative
    `outflows` are also accepted unchecked, which is what makes this
    work for negative bounds.) -/
theorem closing_below_any_bound (n : Int) :
    ∃ e ∈ build [{ week := 1, opening := some 0, inflows := 0,
                   outflows := -n + 1 }], e.closing < n := by
  refine ⟨{ week := 1, opening := 0, inflows := 0, outflows := -n + 1,
            netChange := 0 - (-n + 1), closing := 0 + (0 - (-n + 1)) }, ?_,
    by show 0 + (0 - (-n + 1)) < n; omega⟩
  have h : build [{ week := 1, opening := some 0, inflows := 0,
                    outflows := -n + 1 }]
      = { week := 1, opening := 0, inflows := 0, outflows := -n + 1,
          netChange := 0 - (-n + 1), closing := 0 + (0 - (-n + 1)) }
        :: sched (adaptOpen [{ week := 1, opening := some 0, inflows := 0,
                               outflows := -n + 1 }])
            (adaptFlow [{ week := 1, opening := some 0, inflows := 0,
                          outflows := -n + 1 }])
            (List.range' 2 12) (0 + (0 - (-n + 1))) := rfl
  rw [h]
  exact List.mem_cons_self

/-- **Opening overrides break the chain.**  Week 1 closes at 10500,
    but week 2's row supplies `opening_balance = 999`, and the emitted
    schedule uses 999 verbatim — the running balance is silently
    discarded and `closing(w) = opening(w+1)` fails.  (The repo's own
    test fixture only passes because its hand-supplied openings happen
    to agree with the chain.) -/
theorem override_breaks_chain_example :
    ((build [{ week := 1, opening := some 10000, inflows := 2000,
               outflows := 1500 },
              { week := 2, opening := some 999, inflows := 0,
                outflows := 0 }]).head?).map Entry.closing = some 10500
    ∧ (((build [{ week := 1, opening := some 10000, inflows := 2000,
                  outflows := 1500 },
                 { week := 2, opening := some 999, inflows := 0,
                   outflows := 0 }]).tail).head?).map Entry.opening
      = some 999 := by decide

/-! ## Section B — 13-week forecast skeleton
    (`agents/cashflow_agent.py` ll. 122-151; `rust/src/lib.rs`
    `cashflow_context` ll. 356-394).  Floats are modeled as exact
    rationals (the code's decimal constants are exact decimals:
    4.33 = 433/100, 1.02 = 102/100, factors 0.92/0.97). -/

/-- Collection factor by week: 0.92 for weeks 1-4, 0.97 for weeks
    5-8, 1.00 afterwards. -/
def fcFactor (i : Nat) : Rat :=
  if i ≤ 4 then 92/100 else if i ≤ 8 then 97/100 else 1

/-- Weekly collections: `monthly_revenue / 4.33` times the factor. -/
def fcCollections (rev : Rat) (i : Nat) : Rat := (rev / (433/100)) * fcFactor i

/-- Weekly supplier payments: `monthly_cogs / 4.33` (no factor). -/
def fcPayments (cogs : Rat) : Rat := cogs / (433/100)

/-- Weekly outflows: payments marked up by 2%. -/
def fcOutflows (cogs : Rat) : Rat := fcPayments cogs * (102/100)

/-- Weekly net cash flow. -/
def fcNet (rev cogs : Rat) (i : Nat) : Rat := fcCollections rev i - fcOutflows cogs

/-- Closing balance after week `n`, by the code's recurrence; week 0
    is the opening balance (`current_cash`).  Chained by construction —
    here, and in the code, whose loop threads a single variable. -/
def fcClosing (open' rev cogs : Rat) : Nat → Rat
  | 0 => open'
  | k+1 => fcClosing open' rev cogs k + fcNet rev cogs (k+1)

/-- Sum of the first `n` weekly nets, in the recurrence's order. -/
def sumNet (rev cogs : Rat) : Nat → Rat
  | 0 => 0
  | k+1 => sumNet rev cogs k + fcNet rev cogs (k+1)

/-- One emitted forecast entry (opening, closing) for week `i`. -/
def fcEntry (open' rev cogs : Rat) (i : Nat) : Rat × Rat :=
  (fcClosing open' rev cogs (i - 1),
   fcClosing open' rev cogs (i - 1) + fcNet rev cogs i)

theorem fcEntry_opening (o r c : Rat) (i : Nat) :
    (fcEntry o r c i).1 = fcClosing o r c (i - 1) := rfl

theorem fcEntry_closing (o r c : Rat) (j : Nat) :
    (fcEntry o r c (j + 1)).2 = fcClosing o r c (j + 1) := rfl

/-- Adjacent forecast entries chain: next week's opening is this
    week's closing — by construction (contrast Section A). -/
theorem fc_chain (o r c : Rat) (j : Nat) :
    (fcEntry o r c (j + 2)).1 = (fcEntry o r c (j + 1)).2 := by
  have h : j + 2 - 1 = j + 1 := by omega
  rw [fcEntry_opening, fcEntry_closing, h]

/-- Telescope: the closing balance after `n` weeks is the opening
    balance plus the sum of the weekly nets. -/
theorem fcClosing_eq_sum (o r c : Rat) (n : Nat) :
    fcClosing o r c n = o + sumNet r c n := by
  induction n with
  | zero => simp only [fcClosing, sumNet, Rat.add_zero]
  | succ k ih =>
    simp only [fcClosing, sumNet]
    rw [ih, Rat.add_assoc]

/-- Weeks whose closing balance falls under the threshold
    (`risk_weeks`; default threshold 500000 in both implementations). -/
def fcRiskWeeks (o r c thr : Rat) : List Nat :=
  (List.range' 1 13).filter (fun i => fcClosing o r c i < thr)

theorem mem_fcRiskWeeks {o r c thr : Rat} {i : Nat} :
    i ∈ fcRiskWeeks o r c thr
      ↔ (1 ≤ i ∧ i ≤ 13) ∧ fcClosing o r c i < thr := by
  simp only [fcRiskWeeks, List.mem_filter, List.mem_range', decide_eq_true_eq]
  constructor
  · rintro ⟨⟨j, hj, rfl⟩, hlt⟩
    exact ⟨⟨by omega, by omega⟩, hlt⟩
  · rintro ⟨⟨h1, h2⟩, hlt⟩
    exact ⟨⟨i - 1, by omega, by omega⟩, hlt⟩

/-! ### Concrete rational facts (proved by cross-multiplication through
    `Rat.le_iff` / `Rat.lt_iff`, whose `Int` goals `decide` can check —
    `decide` does not reduce `Rat` comparisons directly). -/

theorem rat_100_pos : (0 : Rat) < 100 := by
  rw [Rat.lt_iff]; decide

theorem factor92_le_one : (92/100 : Rat) ≤ 1 := by
  apply Rat.le_iff_lt_or_eq.mpr
  left
  rw [Rat.div_lt_iff rat_100_pos, Rat.one_mul, Rat.lt_iff]; decide

theorem factor97_le_one : (97/100 : Rat) ≤ 1 := by
  apply Rat.le_iff_lt_or_eq.mpr
  left
  rw [Rat.div_lt_iff rat_100_pos, Rat.one_mul, Rat.lt_iff]; decide

theorem factor92_nonneg : (0 : Rat) ≤ 92/100 := by
  apply Rat.le_iff_lt_or_eq.mpr
  left
  rw [Rat.lt_div_iff rat_100_pos, Rat.zero_mul, Rat.lt_iff]; decide

theorem factor97_nonneg : (0 : Rat) ≤ 97/100 := by
  apply Rat.le_iff_lt_or_eq.mpr
  left
  rw [Rat.lt_div_iff rat_100_pos, Rat.zero_mul, Rat.lt_iff]; decide

theorem val102_pos : (0 : Rat) < 102/100 := by
  rw [Rat.lt_div_iff rat_100_pos, Rat.zero_mul, Rat.lt_iff]; decide

theorem val433_pos : (0 : Rat) < 433/100 := by
  rw [Rat.lt_div_iff rat_100_pos, Rat.zero_mul, Rat.lt_iff]; decide

theorem fcFactor_lo {i : Nat} (h : i ≤ 4) : fcFactor i = 92/100 := by
  unfold fcFactor; rw [if_pos h]

theorem fcFactor_mid {i : Nat} (h1 : ¬ i ≤ 4) (h2 : i ≤ 8) :
    fcFactor i = 97/100 := by
  unfold fcFactor; rw [if_neg h1, if_pos h2]

theorem fcFactor_hi {i : Nat} (h1 : ¬ i ≤ 4) (h2 : ¬ i ≤ 8) :
    fcFactor i = 1 := by
  unfold fcFactor; rw [if_neg h1, if_neg h2]

theorem fcFactor_le_one (i : Nat) : fcFactor i ≤ 1 := by
  by_cases h1 : i ≤ 4
  · rw [fcFactor_lo h1]; exact factor92_le_one
  · by_cases h2 : i ≤ 8
    · rw [fcFactor_mid h1 h2]; exact factor97_le_one
    · rw [fcFactor_hi h1 h2]
      exact Rat.le_iff_lt_or_eq.mpr (Or.inr rfl)

theorem fcFactor_nonneg (i : Nat) : 0 ≤ fcFactor i := by
  by_cases h1 : i ≤ 4
  · rw [fcFactor_lo h1]; exact factor92_nonneg
  · by_cases h2 : i ≤ 8
    · rw [fcFactor_mid h1 h2]; exact factor97_nonneg
    · rw [fcFactor_hi h1 h2]
      exact Rat.le_of_lt (by rw [Rat.lt_iff]; decide)

theorem div_nonneg_of {x y : Rat} (hx : 0 ≤ x) (hy : 0 < y) :
    0 ≤ x / y := by
  rw [Rat.div_def]
  exact Rat.mul_nonneg hx (Rat.le_of_lt (Rat.inv_pos.mpr hy))

/-- Collections never exceed the un-factored weekly revenue (for
    non-negative revenue): the factor is at most 1. -/
theorem fcCollections_le {rev : Rat} (hrev : 0 ≤ rev) (i : Nat) :
    fcCollections rev i ≤ rev / (433/100) := by
  have hnn : 0 ≤ rev / (433/100) := div_nonneg_of hrev val433_pos
  unfold fcCollections
  calc (rev / (433/100)) * fcFactor i ≤ (rev / (433/100)) * 1 :=
        Rat.mul_le_mul_of_nonneg_left (fcFactor_le_one i) hnn
    _ = rev / (433/100) := Rat.mul_one _

theorem fcPayments_nonneg {c : Rat} (hc : 0 ≤ c) : 0 ≤ fcPayments c :=
  div_nonneg_of hc val433_pos

theorem fcOutflows_nonneg {c : Rat} (hc : 0 ≤ c) : 0 ≤ fcOutflows c :=
  Rat.mul_nonneg (fcPayments_nonneg hc) (Rat.le_of_lt val102_pos)

/-- The weekly net never exceeds the week's collections (for
    non-negative COGS): outflows only subtract. -/
theorem fcNet_le_collections {r c : Rat} (hc : 0 ≤ c) (i : Nat) :
    fcNet r c i ≤ fcCollections r i := by
  have ho := fcOutflows_nonneg hc
  have hcalc : fcCollections r i - (fcCollections r i - fcOutflows c)
      = fcOutflows c := by
    rw [Rat.sub_eq_add_neg, Rat.sub_eq_add_neg, Rat.neg_add, Rat.neg_neg,
      ← Rat.add_assoc, Rat.add_neg_cancel, Rat.zero_add]
  unfold fcNet
  rw [Rat.le_iff_sub_nonneg, hcalc]
  exact ho

/-! ## Section C — agent orchestration
    (`orchestration/orchestrator.py` ll. 30-36, 38-88) -/

inductive Agent | AR | AP | INV | CF
  deriving DecidableEq, BEq, Repr

instance : LawfulBEq Agent where
  eq_of_beq := by
    intro a b h
    cases a <;> cases b <;> first | rfl | cases h
  rfl := by
    intro a
    cases a <;> rfl

/-- The fixed dependency graph (ll. 30-36): cashflow runs after AR,
    AP and inventory; the others are sources. -/
def depsOn : Agent → List Agent
  | .CF => [.AR, .AP, .INV]
  | _ => []

/-- A rank witnessing acyclicity of the real graph. -/
def rankOn : Agent → Nat
  | .CF => 1
  | _ => 0

def agents : List Agent := [.AR, .AP, .INV, .CF]

/-- Kahn scan: the first pending agent all of whose dependencies are
    already done.  (The code uses a FIFO queue seeded in dict order;
    any ready-first scan produces a valid order — the properties
    proved below are scan-independent.) -/
def select (d : Agent → List Agent) (l : List Agent) (done : List Agent) :
    Option Agent :=
  match l with
  | [] => none
  | a :: rest => if d a ⊆ done then some a else select d rest done

/-- Closure invariant: every dependency of every pending agent is
    done or still pending. -/
def edgesOn (d : Agent → List Agent) (done l : List Agent) : Prop :=
  ∀ a ∈ l, d a ⊆ done ++ l

/-- Stratification: a rank strictly decreasing along every dependency
    edge that stays within the pending list (acyclicity witness). -/
def StratOn (d : Agent → List Agent) (ρ : Agent → Nat) (l : List Agent) :
    Prop :=
  ∀ a ∈ l, ∀ x ∈ d a, x ∈ l → ρ x < ρ a

/-- "Dependencies respected": every dependency of every scheduled
    agent appears strictly before it in the output. -/
def depsRespected (d : Agent → List Agent) (out : List Agent) : Prop :=
  ∀ a pre post, out = pre ++ a :: post → ∀ x ∈ d a, x ∈ pre

theorem select_cons (d : Agent → List Agent) (b : Agent) (l done : List Agent) :
    select d (b :: l) done
      = if d b ⊆ done then some b else select d l done := rfl

theorem select_spec {d : Agent → List Agent} {l done : List Agent} {a : Agent}
    (h : select d l done = some a) : a ∈ l ∧ d a ⊆ done := by
  induction l with
  | nil => simp [select] at h
  | cons b l ih =>
    rw [select_cons] at h
    by_cases hb : d b ⊆ done
    · rw [if_pos hb] at h
      cases h
      exact ⟨List.mem_cons_self, hb⟩
    · rw [if_neg hb] at h
      obtain ⟨h1, h2⟩ := ih h
      exact ⟨List.mem_cons_of_mem b h1, h2⟩

theorem select_cases (d : Agent → List Agent) (l done : List Agent) :
    (∃ a, select d l done = some a) ∨ select d l done = none := by
  cases h : select d l done with
  | none => exact Or.inr rfl
  | some a => exact Or.inl ⟨a, rfl⟩

theorem edgesOn_subset {d : Agent → List Agent}
    {done done' l l' : List Agent} (he : edgesOn d done l)
    (hl : ∀ a ∈ l', a ∈ l)
    (hmid : ∀ x ∈ l, x ∈ done' ∨ x ∈ l')
    (hd : ∀ x ∈ done, x ∈ done') :
    edgesOn d done' l' := by
  intro a ha x hx
  have h := he a (hl a ha) hx
  rcases List.mem_append.mp h with h | h
  · exact List.mem_append_left _ (hd x h)
  · rcases hmid x h with h' | h'
    · exact List.mem_append_left _ h'
    · exact List.mem_append_right _ h'

theorem exists_min (ρ : Agent → Nat) :
    ∀ (l : List Agent), l ≠ [] →
      ∃ a ∈ l, ∀ b ∈ l, ρ a ≤ ρ b := by
  intro l
  induction l with
  | nil => intro h; exact absurd rfl h
  | cons a l ih =>
    intro _
    cases l with
    | nil =>
      refine ⟨a, List.mem_cons_self, ?_⟩
      intro b hb
      rcases List.mem_cons.mp hb with rfl | hb
      · exact (by omega)
      · cases hb
    | cons b l =>
      obtain ⟨m, hm_mem, hm_min⟩ := ih (by simp)
      by_cases h : ρ a ≤ ρ m
      · refine ⟨a, List.mem_cons_self, ?_⟩
        intro x hx
        rcases List.mem_cons.mp hx with rfl | hx'
        · exact (by omega)
        · exact Nat.le_trans h (hm_min x hx')
      · have h' : ρ m ≤ ρ a := by omega
        refine ⟨m, List.mem_cons_of_mem a hm_mem, ?_⟩
        intro x hx
        rcases List.mem_cons.mp hx with rfl | hx'
        · exact h'
        · exact hm_min x hx'

/-- In a closed, stratified pending list some agent is always ready:
    a minimum-rank agent's dependencies cannot stay pending. -/
theorem exists_ready {d : Agent → List Agent} {ρ : Agent → Nat}
    {done l : List Agent} (he : edgesOn d done l) (hs : StratOn d ρ l)
    (hne : l ≠ []) : ∃ a ∈ l, d a ⊆ done := by
  obtain ⟨a, ha_mem, ha_min⟩ := exists_min ρ l hne
  refine ⟨a, ha_mem, fun x hx => ?_⟩
  have h := he a ha_mem hx
  rcases List.mem_append.mp h with h | h
  · exact h
  · have hlt : ρ x < ρ a := hs a ha_mem x hx h
    have hle : ρ a ≤ ρ x := ha_min x h
    omega

theorem select_some_of_exists {d : Agent → List Agent} {l done : List Agent}
    (h : ∃ a ∈ l, d a ⊆ done) : ∃ a, select d l done = some a := by
  induction l with
  | nil => obtain ⟨a, ha, _⟩ := h; cases ha
  | cons b l ih =>
    by_cases hb : d b ⊆ done
    · exact ⟨b, by rw [select_cons, if_pos hb]⟩
    · obtain ⟨a, ha_mem, ha_sub⟩ := h
      have ha_tail : a ∈ l := by
        rcases List.mem_cons.mp ha_mem with rfl | h'
        · exact absurd ha_sub hb
        · exact h'
      obtain ⟨a', ha'⟩ := ih ⟨a, ha_tail, ha_sub⟩
      exact ⟨a', by rw [select_cons, if_neg hb]; exact ha'⟩

/-- Bounded Kahn run.  Returns `none` when the pending list cannot be
    emptied within the fuel (a dependency cycle); the Python code
    instead falls back to appending the leftovers — modeled by
    `topoSortOrFallback` below. -/
def schedule (d : Agent → List Agent) :
    Nat → List Agent → List Agent → Option (List Agent)
  | 0, l, _ => if l.isEmpty then some [] else none
  | fuel+1, l, done =>
    match select d l done with
    | none => if l.isEmpty then some [] else none
    | some a => (schedule d fuel (l.erase a) (a :: done)).map (a :: ·)

def topoSort (d : Agent → List Agent) (l : List Agent) :
    Option (List Agent) :=
  schedule d (l.length + 1) l []

/-- The Python `_topological_sort` cycle behaviour (ll. 85-88): keep
    the order built so far and append the unschedulable remainder in
    its original relative order. -/
def topoSortOrFallback (d : Agent → List Agent) (l : List Agent) :
    List Agent :=
  (topoSort d l).getD l

theorem schedule_zero (d : Agent → List Agent) (l done : List Agent) :
    schedule d 0 l done = if l.isEmpty then some [] else none := rfl

theorem schedule_succ (d : Agent → List Agent) (fuel : Nat)
    (l done : List Agent) :
    schedule d (fuel + 1) l done = match select d l done with
      | none => if l.isEmpty then some [] else none
      | some a => (schedule d fuel (l.erase a) (a :: done)).map (a :: ·) :=
  rfl

theorem schedule_succ_some (d : Agent → List Agent) (fuel : Nat)
    (l done : List Agent) {a : Agent} (h : select d l done = some a) :
    schedule d (fuel + 1) l done
      = (schedule d fuel (l.erase a) (a :: done)).map (a :: ·) := by
  rw [schedule_succ, h]

theorem schedule_succ_none (d : Agent → List Agent) (fuel : Nat)
    (l done : List Agent) (h : select d l done = none)
    (hne : ¬ l.isEmpty = true) :
    schedule d (fuel + 1) l done = none := by
  rw [schedule_succ, h, if_neg hne]

theorem map_cons_eq_some {x : Option (List Agent)} {a : Agent}
    {out : List Agent} (h : x.map (a :: ·) = some out) :
    ∃ out', x = some out' ∧ out = a :: out' := by
  cases x with
  | none => simp at h
  | some out' =>
    refine ⟨out', rfl, ?_⟩
    have h' : (some (a :: out') : Option (List Agent)) = some out := h
    exact (Option.some.inj h').symm

/-- A successful run schedules every obligation exactly once: the
    output is a permutation of the pending list. -/
theorem schedule_perm {d : Agent → List Agent} :
    ∀ {fuel l done out}, schedule d fuel l done = some out →
      out.Perm l := by
  intro fuel
  induction fuel with
  | zero =>
    intro l done out h
    cases l with
    | nil =>
      rw [schedule_zero] at h
      simp at h
      subst h
      exact List.Perm.refl _
    | cons b l =>
      rw [schedule_zero] at h
      simp at h
  | succ fuel ih =>
    intro l done out h
    obtain (⟨a₀, hsel⟩ | hnone) := select_cases d l done
    · rw [schedule_succ_some d fuel l done hsel] at h
      obtain ⟨out', hrec, hout⟩ := map_cons_eq_some h
      subst hout
      have hperm : out'.Perm (l.erase a₀) := ih hrec
      have hamem : a₀ ∈ l := (select_spec hsel).1
      exact (List.Perm.cons a₀ hperm).trans
        (List.perm_cons_erase hamem).symm
    · cases l with
      | nil =>
        rw [schedule_succ, hnone] at h
        simp at h
        subst h
        exact List.Perm.refl _
      | cons b l =>
        have hcon : schedule d (fuel + 1) (b :: l) done = none :=
          schedule_succ_none d fuel _ _ hnone (by simp)
        rw [hcon] at h
        cases h

/-- A successful run respects dependencies: every dependency of every
    scheduled agent is already done or appears strictly before it. -/
theorem schedule_ordered {d : Agent → List Agent} :
    ∀ {fuel l done out}, schedule d fuel l done = some out →
      edgesOn d done l →
      ∀ a pre post, out = pre ++ a :: post →
        ∀ x ∈ d a, x ∈ done ∨ x ∈ pre := by
  intro fuel
  induction fuel with
  | zero =>
    intro l done out h _he a pre post hsplit x _
    cases l with
    | nil =>
      rw [schedule_zero] at h
      simp at h
      subst h
      cases pre <;> simp at hsplit
    | cons b l =>
      rw [schedule_zero] at h
      simp at h
  | succ fuel ih =>
    intro l done out h he a pre post hsplit x hx
    obtain (⟨a₀, hsel⟩ | hnone) := select_cases d l done
    · rw [schedule_succ_some d fuel l done hsel] at h
      obtain ⟨out', hrec, hout⟩ := map_cons_eq_some h
      subst hout
      have he' : edgesOn d (a₀ :: done) (l.erase a₀) :=
        edgesOn_subset he (fun y hy => List.mem_of_mem_erase hy)
          (fun y hy => by
            by_cases hy0 : y = a₀
            · subst hy0; exact Or.inl List.mem_cons_self
            · exact Or.inr ((List.mem_erase_of_ne hy0).mpr hy))
          (fun y hy => List.mem_cons_of_mem a₀ hy)
      cases pre with
      | nil =>
        have h1 : a₀ = a := List.cons.inj hsplit |>.1
        subst h1
        exact Or.inl ((select_spec hsel).2 hx)
      | cons p pre' =>
        have hsplit' : a₀ :: out' = p :: (pre' ++ a :: post) := hsplit
        have h1 : a₀ = p := List.cons.inj hsplit' |>.1
        have h2 : out' = pre' ++ a :: post := List.cons.inj hsplit' |>.2
        have ih' := ih hrec he' a pre' post h2 x hx
        rcases ih' with h' | h'
        · rcases List.mem_cons.mp h' with rfl | h''
          · rw [h1]; exact Or.inr List.mem_cons_self
          · exact Or.inl h''
        · exact Or.inr (List.mem_cons_of_mem p h')
    · cases l with
      | nil =>
        rw [schedule_succ, hnone] at h
        simp at h
        subst h
        cases pre <;> simp at hsplit
      | cons b l =>
        have hcon : schedule d (fuel + 1) (b :: l) done = none :=
          schedule_succ_none d fuel _ _ hnone (by simp)
        rw [hcon] at h
        cases h

/-- Completeness: a closed, stratified pending list always schedules
    in full, given fuel ≥ length + 1. -/
theorem schedule_complete {d : Agent → List Agent} {ρ : Agent → Nat} :
    ∀ (n : Nat) (l done : List Agent), l.length ≤ n →
      edgesOn d done l → StratOn d ρ l →
      ∃ out, schedule d (n + 1) l done = some out := by
  intro n
  induction n with
  | zero =>
    intro l done hlen _ _
    cases l with
    | nil => exact ⟨[], rfl⟩
    | cons a l => simp at hlen
  | succ n ih =>
    intro l done hlen he hs
    cases hl : l with
    | nil => exact ⟨[], rfl⟩
    | cons a₀ l₀ =>
      subst hl
      obtain ⟨a, ha_mem, ha_sub⟩ :=
        exists_ready he hs (by simp)
      obtain ⟨a₁, hsel⟩ := select_some_of_exists ⟨a, ha_mem, ha_sub⟩
      rw [schedule_succ_some d (n + 1) _ done hsel]
      have hlen' : ((a₀ :: l₀).erase a₁).length ≤ n := by
        have h1 := List.length_erase_of_mem (select_spec hsel).1
        omega
      have he' : edgesOn d (a₁ :: done) ((a₀ :: l₀).erase a₁) :=
        edgesOn_subset he (fun y hy => List.mem_of_mem_erase hy)
          (fun y hy => by
            by_cases hy0 : y = a₁
            · subst hy0; exact Or.inl List.mem_cons_self
            · exact Or.inr ((List.mem_erase_of_ne hy0).mpr hy))
          (fun y hy => List.mem_cons_of_mem a₁ hy)
      have hs' : StratOn d ρ ((a₀ :: l₀).erase a₁) :=
        fun a ha x hx hxl =>
          hs a (List.mem_of_mem_erase ha) x hx (List.mem_of_mem_erase hxl)
      obtain ⟨out, hout⟩ := ih _ _ hlen' he' hs'
      exact ⟨a₁ :: out, by rw [hout]; rfl⟩

theorem edgesOn_real : edgesOn depsOn [] agents := by
  intro a _ha x hx
  cases a
  · exact absurd hx List.not_mem_nil
  · exact absurd hx List.not_mem_nil
  · exact absurd hx List.not_mem_nil
  · show x ∈ agents
    rcases List.mem_cons.mp hx with rfl | hx
    · exact List.mem_cons_self
    rcases List.mem_cons.mp hx with rfl | hx
    · exact List.mem_cons_of_mem _ List.mem_cons_self
    rcases List.mem_cons.mp hx with rfl | hx
    · exact List.mem_cons_of_mem _ (List.mem_cons_of_mem _ List.mem_cons_self)
    · exact absurd hx List.not_mem_nil

theorem stratOn_real : StratOn depsOn rankOn agents := by
  intro a _ha x hx _
  cases a
  · exact absurd hx List.not_mem_nil
  · exact absurd hx List.not_mem_nil
  · exact absurd hx List.not_mem_nil
  · rcases List.mem_cons.mp hx with rfl | hx
    · decide
    rcases List.mem_cons.mp hx with rfl | hx
    · decide
    rcases List.mem_cons.mp hx with rfl | hx
    · decide
    · exact absurd hx List.not_mem_nil

/-- The real graph schedules, in the code's own order. -/
theorem topoSort_real : topoSort depsOn agents = some agents := by
  decide

/-- …and that run is complete, duplicate-free, and dependency-ordered. -/
theorem topoSort_real_complete :
    ∃ out, topoSort depsOn agents = some out ∧ out.Perm agents
      ∧ depsRespected depsOn out := by
  obtain ⟨out, hout⟩ := schedule_complete (n := agents.length) agents []
    (by omega) edgesOn_real stratOn_real
  refine ⟨out, hout, schedule_perm hout, ?_⟩
  intro a pre post hsplit x hx
  have h := schedule_ordered hout edgesOn_real a pre post hsplit x hx
  rcases h with h | h
  · cases h
  · exact h

/-! ### Cycle behaviour — where the code and the invariant part ways -/

/-- A two-agent dependency cycle. -/
def depsCyc : Agent → List Agent
  | .AR => [.AP]
  | .AP => [.AR]
  | _ => []

theorem topoSort_cycle_none : topoSort depsCyc [.AR, .AP] = none := by
  decide

/-- With the Python fallback, the cyclic pair is emitted in its
    original order… -/
theorem fallback_cycle :
    topoSortOrFallback depsCyc [.AR, .AP] = [.AR, .AP] := by
  simp [topoSortOrFallback, topoSort_cycle_none]

/-- …which violates the dependency order: AP must precede AR
    (AR depends on AP) but follows it.  The code only logs a warning
    (l. 85). -/
theorem fallback_cycle_violates :
    ¬ depsRespected depsCyc (topoSortOrFallback depsCyc [.AR, .AP]) := by
  rw [fallback_cycle]
  intro h
  have hmem := h .AR [] [.AP] rfl .AP List.mem_cons_self
  cases hmem

/-- Dependencies pointing at capabilities with no registered agent
    are silently dropped before scheduling (l. 65:
    `present_deps = deps & set(capability_to_agent.keys())`).
    Here: if the inventory agent were missing, cashflow would run
    without waiting for it. -/
def knownDeps (known : List Agent) (a : Agent) : List Agent :=
  (depsOn a).filter (· ∈ known)

theorem knownDeps_drops_unknown :
    knownDeps [.AR, .AP, .INV] .CF = [.AR, .AP, .INV]
      ∧ knownDeps [.AR, .AP] .CF = [.AR, .AP] := by
  decide

/-- `capability_to_agent` is a dict comprehension (ll. 54-56): a
    second agent advertising the same capability silently replaces
    the first, which then never runs. -/
def capabilityToAgent (caps : List (String × Agent)) :
    List (String × Agent) :=
  caps.foldl (fun acc p => (p.1, p.2) :: acc.filter (fun q => q.1 ≠ p.1)) []

theorem capability_collapse :
    capabilityToAgent [("cash", .AR), ("cash", .AP)]
      = [("cash", .AP)] := by
  decide

/-! ## Section D — AP early-payment discount rule
    (`agents/ap_agent.py` ll. 86-125; `rust/src/lib.rs` `ap_context`
    ll. 110-176) -/

inductive Decision | TAKE | SKIP | REVIEW
  deriving DecidableEq, Repr

/-- Days gained by paying early, floored at 1:
    `max((due_date - discount_deadline).days, 1)`. -/
def extraDays (due discountDeadline : Int) : Int :=
  if 1 ≤ due - discountDeadline then due - discountDeadline else 1

theorem extraDays_ge_one (a b : Int) : 1 ≤ extraDays a b := by
  unfold extraDays
  split <;> omega

theorem extraDays_of_gt {a b : Int} (h : b < a) :
    extraDays a b = a - b := by
  unfold extraDays
  rw [if_pos (by omega)]

/-- The TAKE/SKIP comparison, with the code's float division
    cross-multiplied into exact natural arithmetic (basis points).
    The code takes the discount iff
    `(disc/(1-disc)) * (365/extra) > cost_of_capital`; with
    disc = discBps/10000, cap = capBps/10000 and disc < 100%, that
    strict inequality is exactly
    `discBps * 365 * 10000 > capBps * (10000 - discBps) * extra`. -/
def decideOn (discBps capBps extra : Nat) : Decision :=
  if capBps * (10000 - discBps) * extra < discBps * 365 * 10000
  then Decision.TAKE else Decision.SKIP

/-- Unparseable dates yield REVIEW (Python only; the Rust core has no
    REVIEW path — see NOTES). -/
def decideOpt (due discountDeadline : Option Int)
    (discBps capBps : Nat) : Decision :=
  match due, discountDeadline with
  | some d, some dl => decideOn discBps capBps (extraDays d dl).toNat
  | _, _ => Decision.REVIEW

theorem decideOn_take_iff {disc cap extra : Nat} :
    decideOn disc cap extra = Decision.TAKE ↔
      cap * (10000 - disc) * extra < disc * 365 * 10000 := by
  unfold decideOn
  constructor
  · intro h
    by_cases hc : cap * (10000 - disc) * extra < disc * 365 * 10000
    · exact hc
    · rw [if_neg hc] at h; cases h
  · intro h
    rw [if_pos h]

theorem decideOn_skip_iff {disc cap extra : Nat} :
    decideOn disc cap extra = Decision.SKIP ↔
      ¬ cap * (10000 - disc) * extra < disc * 365 * 10000 := by
  unfold decideOn
  constructor
  · intro h hc
    rw [if_pos hc] at h; cases h
  · intro h; rw [if_neg h]

/-- A zero discount is never taken: the gain side is 0 and the strict
    inequality cannot hold. -/
theorem decideOn_zero_disc {cap extra : Nat} :
    decideOn 0 cap extra = Decision.SKIP := by
  rw [decideOn_skip_iff]
  omega

/-- With a zero cost of capital, every positive discount is taken. -/
theorem decideOn_zero_cap {disc extra : Nat} (hd : 1 ≤ disc) :
    decideOn disc 0 extra = Decision.TAKE := by
  rw [decideOn_take_iff]
  simp only [Nat.zero_mul]
  exact Nat.mul_pos (Nat.mul_pos hd (by decide)) (by decide)

/-- Rust/Python default divergence, machine-checked.  The Python
    fallback defaults `cost_of_capital` to 0.08 (ap_agent.py l. 89);
    the Rust core's `num()` defaults a missing field to 0.0
    (lib.rs l. 6), i.e. capBps = 0 here.  Same invoice (0.5%
    discount, 30 extra days): SKIP under the Python default,
    TAKE under the Rust default. -/
theorem default_divergence :
    decideOn 50 800 30 = Decision.SKIP
      ∧ decideOn 50 0 30 = Decision.TAKE := by
  decide

/-- At a 100% "discount" the code's formula divides by `1 - disc = 0`;
    the cross-multiplied form degenerates to "always TAKE".  The two
    agree nowhere here — real data must keep disc < 100%. -/
theorem decideOn_full_discount {cap extra : Nat} :
    decideOn 10000 cap extra = Decision.TAKE := by
  rw [decideOn_take_iff]
  have hz : cap * (10000 - 10000) * extra = 0 := by simp
  rw [hz]
  decide

theorem decideOpt_review_left {dl : Option Int} {disc cap : Nat} :
    decideOpt none dl disc cap = Decision.REVIEW := by
  cases dl <;> rfl

theorem decideOpt_review_right {due : Option Int} {disc cap : Nat} :
    decideOpt due none disc cap = Decision.REVIEW := by
  cases due <;> rfl

theorem decideOpt_some {d dl : Int} {disc cap : Nat} :
    decideOpt (some d) (some dl) disc cap
      = decideOn disc cap (extraDays d dl).toNat := rfl

end WCO
