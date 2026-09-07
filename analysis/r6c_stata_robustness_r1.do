version 16.0
clear all
set more off
capture log close _all

* ============================================================
* OMOSSP R6C — Local Stata 17 Independent Robustness Verification R1
* Run under Stata 17 using version 16.0 compatibility semantics.
*
* 24m data SHA-256:
* 814eef9868630ac94c0d59f15733b894c39dff78785a81f535cbcbf0f00c8346
*
* 36m data SHA-256:
* 8fe2f2cbeffc2e94bbfdb0df70861607ec6947b27c231c247fc5ff1557cd975b
*
* ASSOCIATIONAL / MEASUREMENT-VALIDATION ONLY.
* NO CAUSAL INTERPRETATION.
* ============================================================

local DATA24 "data/r4_corrected/r4_corrected_project_month_panel.dta"
local DATA36 "data/r6_36m/r6_36m_corrected_project_month_panel.dta"
local OUT    "results/r6c"

capture mkdir "results"
capture mkdir "`OUT'"

log using "`OUT'/r6c_stata_robustness.log", text replace name(r6c)

file open r6cfh using "`OUT'/r6c_stata_robustness_high_precision.csv", write text replace
file write r6cfh "spec_id,family,model,N,projects,term,b,se,p" _n

capture program drop omossp_r6c_run
program define omossp_r6c_run
    syntax, SPEC(string) FAMILY(string) MODEL(string) Y(varname) X(varlist) SAMPLE(varname) EXPN(integer) EXPG(integer)

    quietly xtreg `y' `x' i.month_id if `sample'==1, fe vce(cluster pid)

    if (e(N) != `expn') {
        display as error "R6C_N_ASSERT_FAIL spec=`spec' observed=" e(N) " expected=`expn'"
        exit 459
    }
    if (e(N_g) != `expg') {
        display as error "R6C_PROJECT_ASSERT_FAIL spec=`spec' observed=" e(N_g) " expected=`expg'"
        exit 459
    }

    estimates store E_`spec'
    estimates save "$R6C_OUT/r6c_`spec'.ster", replace

    foreach term of local x {
        scalar __b  = _b[`term']
        scalar __se = _se[`term']
        scalar __p  = 2*ttail(e(df_r), abs(__b/__se))
        file write r6cfh "`spec',`family',`model'," %12.0f (e(N)) "," %12.0f (e(N_g)) ",`term'," %24.17g (__b) "," %24.17g (__se) "," %24.17g (__p) _n
    }
end

global R6C_OUT "`OUT'"

* ============================================================
* PART I — 24-MONTH ROBUSTNESS: 2024-01..2025-12
* ============================================================

use "`DATA24'", clear

isid project_id month, sort
quietly count
assert r(N)==21168
quietly levelsof project_id, local(P24)
local NP24 : word count `P24'
assert `NP24'==882

encode project_id, gen(pid)
xtset pid month_id

assert inrange(elig_A,0,1)
assert inrange(elig_B,0,1)
assert inrange(elig_C,0,1)
assert inrange(elig_D,0,1)

bysort pid: egen nA = total(elig_A)
bysort pid: egen nB = total(elig_B)
bysort pid: egen nC = total(elig_C)
bysort pid: egen nD = total(elig_D)

gen s_A2  = elig_A==1 & nA>=2
gen s_B2  = elig_B==1 & nB>=2
gen s_C2  = elig_C==1 & nC>=2
gen s_D2  = elig_D==1 & nD>=2

gen s_A6  = elig_A==1 & nA>=6
gen s_B6  = elig_B==1 & nB>=6
gen s_C6  = elig_C==1 & nC>=6
gen s_D6  = elig_D==1 & nD>=6

gen s_A12 = elig_A==1 & nA>=12
gen s_B12 = elig_B==1 & nB>=12
gen s_C12 = elig_C==1 & nC>=12
gen s_D12 = elig_D==1 & nD>=12

* Frozen common-support rule.
gen common_complete = !missing(ln_resolution, ln_open_age, asinh_backlog, ln_issues_new, ln_contributors)
bysort pid: egen nCOMMON = total(common_complete)
gen s_COMMON = common_complete==1 & nCOMMON>=2

quietly count if s_COMMON
assert r(N)==13781
quietly egen tagCOMMON = tag(pid) if s_COMMON
quietly count if tagCOMMON
assert r(N)==805

* Secondary measurement-observability diagnostic.
gen md_complete = !missing(ln_issues_new, ln_contributors)
bysort pid: egen nMD = total(md_complete)
gen s_MD = md_complete==1 & nMD>=2
gen resolution_observed = !missing(ln_resolution)

quietly count if s_MD
assert r(N)==21072
quietly egen tagMD = tag(pid) if s_MD
quietly count if tagMD
assert r(N)==878
assert !missing(asinh_net_code_lines) if s_MD

* ----- R6.1 Minimum usable-month robustness -----
omossp_r6c_run, spec(R6_1_A_GE6)  family(R6_1_MIN_USABLE_MONTHS) model(A) y(ln_open_age)     x(ln_resolution ln_issues_new ln_contributors) sample(s_A6)  expn(13451) expg(717)
omossp_r6c_run, spec(R6_1_A_GE12) family(R6_1_MIN_USABLE_MONTHS) model(A) y(ln_open_age)     x(ln_resolution ln_issues_new ln_contributors) sample(s_A12) expn(12444) expg(600)

omossp_r6c_run, spec(R6_1_B_GE6)  family(R6_1_MIN_USABLE_MONTHS) model(B) y(asinh_backlog)   x(ln_resolution ln_issues_new ln_contributors) sample(s_B6)  expn(13471) expg(718)
omossp_r6c_run, spec(R6_1_B_GE12) family(R6_1_MIN_USABLE_MONTHS) model(B) y(asinh_backlog)   x(ln_resolution ln_issues_new ln_contributors) sample(s_B12) expn(12465) expg(601)

omossp_r6c_run, spec(R6_1_C_GE6)  family(R6_1_MIN_USABLE_MONTHS) model(C) y(ln_resolution)   x(ln_issues_new ln_contributors) sample(s_C6)  expn(13471) expg(718)
omossp_r6c_run, spec(R6_1_C_GE12) family(R6_1_MIN_USABLE_MONTHS) model(C) y(ln_resolution)   x(ln_issues_new ln_contributors) sample(s_C12) expn(12465) expg(601)

omossp_r6c_run, spec(R6_1_D_GE6)  family(R6_1_MIN_USABLE_MONTHS) model(D) y(ln_open_age)     x(ln_issues_new ln_contributors) sample(s_D6)  expn(20852) expg(871)
omossp_r6c_run, spec(R6_1_D_GE12) family(R6_1_MIN_USABLE_MONTHS) model(D) y(ln_open_age)     x(ln_issues_new ln_contributors) sample(s_D12) expn(20846) expg(870)

* ----- R6.2 Common-support robustness -----
omossp_r6c_run, spec(R6_2_A_COMMON) family(R6_2_COMMON_SUPPORT) model(A) y(ln_open_age)     x(ln_resolution ln_issues_new ln_contributors) sample(s_COMMON) expn(13781) expg(805)
omossp_r6c_run, spec(R6_2_B_COMMON) family(R6_2_COMMON_SUPPORT) model(B) y(asinh_backlog)   x(ln_resolution ln_issues_new ln_contributors) sample(s_COMMON) expn(13781) expg(805)
omossp_r6c_run, spec(R6_2_C_COMMON) family(R6_2_COMMON_SUPPORT) model(C) y(ln_resolution)   x(ln_issues_new ln_contributors) sample(s_COMMON) expn(13781) expg(805)
omossp_r6c_run, spec(R6_2_D_COMMON) family(R6_2_COMMON_SUPPORT) model(D) y(ln_open_age)     x(ln_issues_new ln_contributors) sample(s_COMMON) expn(13781) expg(805)

* ----- R6.3 Auxiliary signed net-code context -----
assert !missing(asinh_net_code_lines) if s_A2
assert !missing(asinh_net_code_lines) if s_B2
assert !missing(asinh_net_code_lines) if s_C2
assert !missing(asinh_net_code_lines) if s_D2

omossp_r6c_run, spec(R6_3_A_AUX_NET_CODE) family(R6_3_AUX_SIGNED_CHANGE_CONTEXT) model(A) y(ln_open_age)   x(ln_resolution ln_issues_new ln_contributors asinh_net_code_lines) sample(s_A2) expn(13781) expg(805)
omossp_r6c_run, spec(R6_3_B_AUX_NET_CODE) family(R6_3_AUX_SIGNED_CHANGE_CONTEXT) model(B) y(asinh_backlog) x(ln_resolution ln_issues_new ln_contributors asinh_net_code_lines) sample(s_B2) expn(13797) expg(805)
omossp_r6c_run, spec(R6_3_C_AUX_NET_CODE) family(R6_3_AUX_SIGNED_CHANGE_CONTEXT) model(C) y(ln_resolution) x(ln_issues_new ln_contributors asinh_net_code_lines) sample(s_C2) expn(13797) expg(805)
omossp_r6c_run, spec(R6_3_D_AUX_NET_CODE) family(R6_3_AUX_SIGNED_CHANGE_CONTEXT) model(D) y(ln_open_age)   x(ln_issues_new ln_contributors asinh_net_code_lines) sample(s_D2) expn(20852) expg(871)

* ----- R6-MD1 Measurement observability -----
omossp_r6c_run, spec(R6_MD1_BASE) family(R6_MD1) model(MD1) y(resolution_observed) x(ln_issues_new ln_contributors) sample(s_MD) expn(21072) expg(878)
omossp_r6c_run, spec(R6_MD1_AUX_NET_CODE) family(R6_MD1) model(MD1) y(resolution_observed) x(ln_issues_new ln_contributors asinh_net_code_lines) sample(s_MD) expn(21072) expg(878)

* ============================================================
* PART II — 36-MONTH TEMPORAL ROBUSTNESS: 2023-01..2025-12
* ============================================================

use "`DATA36'", clear

isid project_id month, sort
quietly count
assert r(N)==30384
quietly levelsof project_id, local(P36)
local NP36 : word count `P36'
assert `NP36'==844

encode project_id, gen(pid)
xtset pid month_id

assert inrange(elig_A,0,1)
assert inrange(elig_B,0,1)
assert inrange(elig_C,0,1)
assert inrange(elig_D,0,1)

bysort pid: egen nA36 = total(elig_A)
bysort pid: egen nB36 = total(elig_B)
bysort pid: egen nC36 = total(elig_C)
bysort pid: egen nD36 = total(elig_D)

gen s_A36 = elig_A==1 & nA36>=2
gen s_B36 = elig_B==1 & nB36>=2
gen s_C36 = elig_C==1 & nC36>=2
gen s_D36 = elig_D==1 & nD36>=2

omossp_r6c_run, spec(R6_4_A_36M) family(R6_4_36M_WINDOW) model(A) y(ln_open_age)   x(ln_resolution ln_issues_new ln_contributors) sample(s_A36) expn(21020) expg(800)
omossp_r6c_run, spec(R6_4_B_36M) family(R6_4_36M_WINDOW) model(B) y(asinh_backlog) x(ln_resolution ln_issues_new ln_contributors) sample(s_B36) expn(21045) expg(800)
omossp_r6c_run, spec(R6_4_C_36M) family(R6_4_36M_WINDOW) model(C) y(ln_resolution) x(ln_issues_new ln_contributors) sample(s_C36) expn(21045) expg(800)
omossp_r6c_run, spec(R6_4_D_36M) family(R6_4_36M_WINDOW) model(D) y(ln_open_age)   x(ln_issues_new ln_contributors) sample(s_D36) expn(29893) expg(834)

file close r6cfh
log close r6c

display "OMOSSP_R6C_STATA_ROBUSTNESS_COMPLETE"
