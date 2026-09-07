version 16.0
clear all
set more off
capture log close _all

* ============================================================
* OMOSSP R5 — Formal Stata Baseline Panel Analysis R1
* AUTHORITY DATA:
* data/r4_corrected/r4_corrected_project_month_panel.dta
* SHA-256:
* 814eef9868630ac94c0d59f15733b894c39dff78785a81f535cbcbf0f00c8346
*
* ASSOCIATIONAL / MEASUREMENT-VALIDATION ONLY.
* NO CAUSAL INTERPRETATION.
* ============================================================

local DATA "data/r4_corrected/r4_corrected_project_month_panel.dta"
local OUT  "results/r5"

capture mkdir "results"
capture mkdir "`OUT'"

log using "`OUT'/r5_stata_baseline.log", text replace name(r5)

use "`DATA'", clear

* ----- Authority / structure checks -----
isid project_id month, sort
assert inrange(elig_A,0,1)
assert inrange(elig_B,0,1)
assert inrange(elig_C,0,1)
assert inrange(elig_D,0,1)

encode project_id, gen(pid)
xtset pid month_id

quietly count
assert r(N)==21168
quietly levelsof pid, local(PIDS)
local NP : word count `PIDS'
assert `NP'==882

* Model-specific minimum-two-month eligibility.
bysort pid: egen nA = total(elig_A)
bysort pid: egen nB = total(elig_B)
bysort pid: egen nC = total(elig_C)
bysort pid: egen nD = total(elig_D)

gen sample_A = elig_A==1 & nA>=2
gen sample_B = elig_B==1 & nB>=2
gen sample_C = elig_C==1 & nC>=2
gen sample_D = elig_D==1 & nD>=2

quietly egen tagA = tag(pid) if sample_A
quietly count if tagA
assert r(N)==805

quietly egen tagB = tag(pid) if sample_B
quietly count if tagB
assert r(N)==805

quietly egen tagC = tag(pid) if sample_C
quietly count if tagC
assert r(N)==805

quietly egen tagD = tag(pid) if sample_D
quietly count if tagD
assert r(N)==871

* ----- Descriptive diagnostics; no sample redefinition -----
summarize ln_resolution ln_open_age asinh_backlog ln_issues_new ln_contributors
xtsum ln_resolution ln_open_age asinh_backlog ln_issues_new ln_contributors

* ============================================================
* MODEL A
* ln(open issue age) on ln(closed issue resolution median)
* + workload context + participation breadth
* project FE + calendar-month FE
* SE clustered by project
* ============================================================
xtreg ln_open_age ln_resolution ln_issues_new ln_contributors i.month_id ///
    if sample_A, fe vce(cluster pid)
estimates store R5_A

scalar A_N       = e(N)
scalar A_Ng      = e(N_g)
scalar A_r2w     = e(r2_w)
scalar A_b_res   = _b[ln_resolution]
scalar A_se_res  = _se[ln_resolution]
scalar A_b_issue = _b[ln_issues_new]
scalar A_se_issue= _se[ln_issues_new]
scalar A_b_contr = _b[ln_contributors]
scalar A_se_contr= _se[ln_contributors]

assert A_N==13781
assert A_Ng==805

* ============================================================
* MODEL B
* unresolved backlog burden on closed-item resolution median
* ============================================================
xtreg asinh_backlog ln_resolution ln_issues_new ln_contributors i.month_id ///
    if sample_B, fe vce(cluster pid)
estimates store R5_B

scalar B_N       = e(N)
scalar B_Ng      = e(N_g)
scalar B_r2w     = e(r2_w)
scalar B_b_res   = _b[ln_resolution]
scalar B_se_res  = _se[ln_resolution]
scalar B_b_issue = _b[ln_issues_new]
scalar B_se_issue= _se[ln_issues_new]
scalar B_b_contr = _b[ln_contributors]
scalar B_se_contr= _se[ln_contributors]

assert B_N==13797
assert B_Ng==805

* ============================================================
* MODEL C
* context sensitivity of closed-item resolution median
* ============================================================
xtreg ln_resolution ln_issues_new ln_contributors i.month_id ///
    if sample_C, fe vce(cluster pid)
estimates store R5_C

scalar C_N       = e(N)
scalar C_Ng      = e(N_g)
scalar C_r2w     = e(r2_w)
scalar C_b_issue = _b[ln_issues_new]
scalar C_se_issue= _se[ln_issues_new]
scalar C_b_contr = _b[ln_contributors]
scalar C_se_contr= _se[ln_contributors]

assert C_N==13797
assert C_Ng==805

* ============================================================
* MODEL D
* context sensitivity of unresolved backlog age
* ============================================================
xtreg ln_open_age ln_issues_new ln_contributors i.month_id ///
    if sample_D, fe vce(cluster pid)
estimates store R5_D

scalar D_N       = e(N)
scalar D_Ng      = e(N_g)
scalar D_r2w     = e(r2_w)
scalar D_b_issue = _b[ln_issues_new]
scalar D_se_issue= _se[ln_issues_new]
scalar D_b_contr = _b[ln_contributors]
scalar D_se_contr= _se[ln_contributors]

assert D_N==20852
assert D_Ng==871

* ----- Machine-readable baseline summary -----
tempname fh
file open `fh' using "`OUT'/r5_stata_baseline_summary.csv", write text replace
file write `fh' "model,N,projects,r2_within,term,b,se" _n

file write `fh' "A," %12.0f (A_N) "," %12.0f (A_Ng) "," %12.8f (A_r2w) ",ln_resolution," %18.10f (A_b_res) "," %18.10f (A_se_res) _n
file write `fh' "A," %12.0f (A_N) "," %12.0f (A_Ng) "," %12.8f (A_r2w) ",ln_issues_new," %18.10f (A_b_issue) "," %18.10f (A_se_issue) _n
file write `fh' "A," %12.0f (A_N) "," %12.0f (A_Ng) "," %12.8f (A_r2w) ",ln_contributors," %18.10f (A_b_contr) "," %18.10f (A_se_contr) _n

file write `fh' "B," %12.0f (B_N) "," %12.0f (B_Ng) "," %12.8f (B_r2w) ",ln_resolution," %18.10f (B_b_res) "," %18.10f (B_se_res) _n
file write `fh' "B," %12.0f (B_N) "," %12.0f (B_Ng) "," %12.8f (B_r2w) ",ln_issues_new," %18.10f (B_b_issue) "," %18.10f (B_se_issue) _n
file write `fh' "B," %12.0f (B_N) "," %12.0f (B_Ng) "," %12.8f (B_r2w) ",ln_contributors," %18.10f (B_b_contr) "," %18.10f (B_se_contr) _n

file write `fh' "C," %12.0f (C_N) "," %12.0f (C_Ng) "," %12.8f (C_r2w) ",ln_issues_new," %18.10f (C_b_issue) "," %18.10f (C_se_issue) _n
file write `fh' "C," %12.0f (C_N) "," %12.0f (C_Ng) "," %12.8f (C_r2w) ",ln_contributors," %18.10f (C_b_contr) "," %18.10f (C_se_contr) _n

file write `fh' "D," %12.0f (D_N) "," %12.0f (D_Ng) "," %12.8f (D_r2w) ",ln_issues_new," %18.10f (D_b_issue) "," %18.10f (D_se_issue) _n
file write `fh' "D," %12.0f (D_N) "," %12.0f (D_Ng) "," %12.8f (D_r2w) ",ln_contributors," %18.10f (D_b_contr) "," %18.10f (D_se_contr) _n

file close `fh'

* Preserve estimates.
estimates restore R5_A
estimates save "`OUT'/r5_A.ster", replace
estimates restore R5_B
estimates save "`OUT'/r5_B.ster", replace
estimates restore R5_C
estimates save "`OUT'/r5_C.ster", replace
estimates restore R5_D
estimates save "`OUT'/r5_D.ster", replace

log close r5
display "OMOSSP_R5_STATA_BASELINE_COMPLETE"
