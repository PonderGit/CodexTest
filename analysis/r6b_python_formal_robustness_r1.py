#!/usr/bin/env python3
import hashlib
import json
import math
import platform
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

DATA24 = Path("data/r4_corrected/r4_corrected_project_month_panel.dta")
DATA36 = Path("data/r6_36m/r6_36m_corrected_project_month_panel.dta")
R5_SUMMARY = Path("results/r5_python_formal/r5_python_formal_summary.json")
R6_DESIGN = Path("governance/omossp_r6_robustness_design_lock_r1.json")
R6A = Path("governance/omossp_r6a_robustness_feasibility_closeout_r1.json")

OUTDIR = Path("results/r6b_python_formal")
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT_SUMMARY = OUTDIR / "r6b_python_formal_summary.json"
OUT_COEFF = OUTDIR / "r6b_python_formal_coefficients.csv"
OUT_COMPARE = OUTDIR / "r6b_python_comparison_to_r5.csv"
OUT_ENV = OUTDIR / "r6b_python_formal_environment.json"

SHA24 = "814eef9868630ac94c0d59f15733b894c39dff78785a81f535cbcbf0f00c8346"
SHA36 = "8fe2f2cbeffc2e94bbfdb0df70861607ec6947b27c231c247fc5ff1557cd975b"

BASE_MODELS = {
    "A": {"y": "ln_open_age", "x": ["ln_resolution", "ln_issues_new", "ln_contributors"], "elig": "elig_A"},
    "B": {"y": "asinh_backlog", "x": ["ln_resolution", "ln_issues_new", "ln_contributors"], "elig": "elig_B"},
    "C": {"y": "ln_resolution", "x": ["ln_issues_new", "ln_contributors"], "elig": "elig_C"},
    "D": {"y": "ln_open_age", "x": ["ln_issues_new", "ln_contributors"], "elig": "elig_D"},
}

EXPECTED_24_THRESHOLD = {
    ("A", 6): (717, 13451), ("A", 12): (600, 12444),
    ("B", 6): (718, 13471), ("B", 12): (601, 12465),
    ("C", 6): (718, 13471), ("C", 12): (601, 12465),
    ("D", 6): (871, 20852), ("D", 12): (870, 20846),
}
EXPECTED_COMMON = (805, 13781)
EXPECTED_BASELINE_EST = {
    "A": (805, 13781), "B": (805, 13797), "C": (805, 13797), "D": (871, 20852)
}
EXPECTED_36_PRE = {
    "A": (800, 21020), "B": (800, 21045), "C": (800, 21045), "D": (834, 29893)
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_class(x: float) -> str:
    if x > 0:
        return "positive"
    if x < 0:
        return "negative"
    return "zero"


def p05(p: float) -> bool:
    return bool(p < 0.05)


def model_sample(df, elig, min_months):
    counts = df.groupby("project_id")[elig].sum()
    keep = counts[counts >= min_months].index
    sub = df[df["project_id"].isin(keep) & (df[elig] == 1)].copy()
    return sub, int(len(keep)), int(len(sub))


def common_support_sample(df):
    vars_ = ["ln_resolution", "ln_open_age", "asinh_backlog", "ln_issues_new", "ln_contributors"]
    mask = df[vars_].notna().all(axis=1)
    counts = df.loc[mask].groupby("project_id").size()
    keep = counts[counts >= 2].index
    sub = df[mask & df["project_id"].isin(keep)].copy()
    return sub, int(len(keep)), int(len(sub))


def diagnostic_sample(df, include_aux):
    x = ["ln_issues_new", "ln_contributors"]
    if include_aux:
        x.append("asinh_net_code_lines")
    mask = df[x].notna().all(axis=1)
    counts = df.loc[mask].groupby("project_id").size()
    keep = counts[counts >= 2].index
    sub = df[mask & df["project_id"].isin(keep)].copy()
    sub["resolution_observed"] = sub["ln_resolution"].notna().astype(float)
    return sub, x, int(len(keep)), int(len(sub))


def fit_panel(sub, y, x, spec_id, family, model_name, source_window, sample_rule):
    pre_N = int(len(sub))
    pre_projects = int(sub["project_id"].nunique())
    p = sub.set_index(["project_id", "month_id"]).sort_index()
    mod = PanelOLS(
        p[y],
        p[x],
        entity_effects=True,
        time_effects=True,
        drop_absorbed=True,
        check_rank=True,
    )
    res = mod.fit(cov_type="clustered", cluster_entity=True, debiased=True)
    ci = res.conf_int(level=0.95)

    rows = []
    for term in x:
        assert term in res.params.index, (spec_id, term, list(res.params.index))
        rows.append({
            "spec_id": spec_id,
            "family": family,
            "model": model_name,
            "window": source_window,
            "sample_rule": sample_rule,
            "y": y,
            "term": term,
            "b": float(res.params[term]),
            "se": float(res.std_errors[term]),
            "t": float(res.tstats[term]),
            "p": float(res.pvalues[term]),
            "ci95_low": float(ci.loc[term, "lower"]),
            "ci95_high": float(ci.loc[term, "upper"]),
            "sign": sign_class(float(res.params[term])),
            "p_lt_0_05": p05(float(res.pvalues[term])),
            "pre_estimator_N": pre_N,
            "pre_estimator_projects": pre_projects,
            "estimator_N": int(res.nobs),
            "estimator_projects": pre_projects,
            "rsquared_within": float(res.rsquared_within),
            "rsquared_overall": float(res.rsquared_overall),
            "rsquared_between": float(res.rsquared_between),
        })

    return {
        "spec_id": spec_id,
        "family": family,
        "model": model_name,
        "window": source_window,
        "sample_rule": sample_rule,
        "y": y,
        "x": list(x),
        "pre_estimator_N": pre_N,
        "pre_estimator_projects": pre_projects,
        "estimator_N": int(res.nobs),
        "estimator_projects": pre_projects,
        "rsquared_within": float(res.rsquared_within),
        "rsquared_overall": float(res.rsquared_overall),
        "rsquared_between": float(res.rsquared_between),
        "coefficients": rows,
    }


def baseline_lookup():
    r5 = json.loads(R5_SUMMARY.read_text(encoding="utf-8"))
    assert r5["data_sha256"] == SHA24
    lookup = {}
    for model, m in r5["models"].items():
        for c in m["coefficients"]:
            lookup[(model, c["term"])] = c
    return lookup


def compare_to_r5(rows, base):
    out = []
    for r in rows:
        if r["family"] == "R6_MD1":
            continue
        key = (r["model"], r["term"])
        if key not in base:
            # New auxiliary term has no R5 counterpart.
            continue
        b0 = float(base[key]["b"])
        se0 = float(base[key]["se"])
        p0 = float(base[key]["p"])
        b1 = float(r["b"])
        abs_delta = b1 - b0
        rel_abs = abs(abs_delta) / abs(b0) if b0 != 0 else math.nan
        out.append({
            "spec_id": r["spec_id"],
            "family": r["family"],
            "model": r["model"],
            "term": r["term"],
            "r5_b": b0,
            "r6_b": b1,
            "delta_b": abs_delta,
            "absolute_delta_b": abs(abs_delta),
            "relative_absolute_delta_b": rel_abs,
            "r5_se": se0,
            "r6_se": float(r["se"]),
            "r5_p": p0,
            "r6_p": float(r["p"]),
            "direction_match": sign_class(b0) == sign_class(b1),
            "p05_classification_match": p05(p0) == p05(float(r["p"])),
            "interpretation_rule": "DESCRIPTIVE_ONLY__NO_HARD_MAGNITUDE_THRESHOLD__NO_SIGNIFICANCE_ONLY_DECISION",
        })
    return out


def main():
    assert sha256_file(DATA24) == SHA24
    assert sha256_file(DATA36) == SHA36

    design = json.loads(R6_DESIGN.read_text(encoding="utf-8"))
    assert design["status"] == "PASS__R6_ROBUSTNESS_DESIGN_FROZEN__NO_ROBUSTNESS_RESULTS_RUN"
    r6a = json.loads(R6A.read_text(encoding="utf-8"))
    assert r6a["status"] == "PASS__R6A_IMPLEMENTATION_AND_36M_FEASIBILITY_COMPLETE__R6B_FORMAL_ROBUSTNESS_EXECUTION_AUTHORIZED"
    assert r6a["panel36"]["feasibility_gate"] == "PASS__800_GE_500"

    df24 = pd.read_stata(DATA24, convert_categoricals=False)
    df36 = pd.read_stata(DATA36, convert_categoricals=False)
    assert len(df24) == 21168 and df24["project_id"].nunique() == 882
    assert len(df36) == 30384 and df36["project_id"].nunique() == 844
    assert not df24.duplicated(["project_id", "month_id"]).any()
    assert not df36.duplicated(["project_id", "month_id"]).any()

    specs = {}
    rows = []

    # R6.1 Minimum usable-month robustness: all frozen >=6 and >=12 specifications.
    for model, m in BASE_MODELS.items():
        for threshold in (6, 12):
            sub, npj, nt = model_sample(df24, m["elig"], threshold)
            exp_p, exp_n = EXPECTED_24_THRESHOLD[(model, threshold)]
            assert (npj, nt) == (exp_p, exp_n), (model, threshold, npj, nt, exp_p, exp_n)
            sid = f"R6_1_{model}_GE{threshold}"
            result = fit_panel(
                sub, m["y"], m["x"], sid, "R6_1_MIN_USABLE_MONTHS", model, "2024-01..2025-12",
                f"{m['elig']}==1 and project has >={threshold} eligible months"
            )
            specs[sid] = result
            rows.extend(result["coefficients"])

    # R6.2 Common support: identical project-month sample for A-D.
    common, npj, nt = common_support_sample(df24)
    assert (npj, nt) == EXPECTED_COMMON, (npj, nt, EXPECTED_COMMON)
    common_keys = set(zip(common["project_id"], common["month_id"]))
    for model, m in BASE_MODELS.items():
        sid = f"R6_2_{model}_COMMON"
        # Use exactly the frozen common-support rows, not model-specific eligibility.
        assert set(zip(common["project_id"], common["month_id"])) == common_keys
        result = fit_panel(
            common.copy(), m["y"], m["x"], sid, "R6_2_COMMON_SUPPORT", model, "2024-01..2025-12",
            "All five baseline analytic variables observed; project has >=2 common-support months"
        )
        assert result["pre_estimator_N"] == 13781 and result["pre_estimator_projects"] == 805
        specs[sid] = result
        rows.extend(result["coefficients"])

    # R6.3 Add signed net-code-size change as auxiliary context, preserving R5 baseline samples.
    for model, m in BASE_MODELS.items():
        sub, npj, nt = model_sample(df24, m["elig"], 2)
        assert (npj, int(len(sub))) == EXPECTED_BASELINE_EST[model] or model == "A"
        assert sub["asinh_net_code_lines"].isna().sum() == 0
        x = list(m["x"]) + ["asinh_net_code_lines"]
        sid = f"R6_3_{model}_AUX_NET_CODE"
        result = fit_panel(
            sub, m["y"], x, sid, "R6_3_AUX_SIGNED_CHANGE_CONTEXT", model, "2024-01..2025-12",
            "Original R5 model-specific >=2-month sample; add asinh_net_code_lines; no sign/magnitude filtering"
        )
        # Estimator N must match the R5 estimator sample if auxiliary context adds no missingness.
        exp_p, exp_n = EXPECTED_BASELINE_EST[model]
        assert result["estimator_projects"] == exp_p
        assert result["estimator_N"] == exp_n, (sid, result["estimator_N"], exp_n)
        specs[sid] = result
        rows.extend(result["coefficients"])

    # R6.4 36-month temporal window using already-rebuilt frozen R6A panel.
    for model, m in BASE_MODELS.items():
        sub, npj, nt = model_sample(df36, m["elig"], 2)
        exp_p, exp_n = EXPECTED_36_PRE[model]
        assert (npj, nt) == (exp_p, exp_n), (model, npj, nt, exp_p, exp_n)
        sid = f"R6_4_{model}_36M"
        result = fit_panel(
            sub, m["y"], m["x"], sid, "R6_4_36M_WINDOW", model, "2023-01..2025-12",
            f"{m['elig']}==1 and project has >=2 eligible months in frozen 36m panel"
        )
        specs[sid] = result
        rows.extend(result["coefficients"])

    # Secondary R6-MD1. Freeze BOTH base and auxiliary versions so optionality cannot be used post hoc.
    md1_samples = {}
    for label, include_aux in (("BASE", False), ("AUX_NET_CODE", True)):
        sub, x, npj, nt = diagnostic_sample(df24, include_aux)
        sid = f"R6_MD1_{label}"
        result = fit_panel(
            sub, "resolution_observed", x, sid, "R6_MD1", "MD1", "2024-01..2025-12",
            "Verified 24m exposure; outcome=1 iff ln_resolution defined; complete predictors; project >=2 diagnostic months"
        )
        specs[sid] = result
        rows.extend(result["coefficients"])
        md1_samples[label] = {"pre_estimator_projects": npj, "pre_estimator_N": nt, "estimator_N": result["estimator_N"]}

    base = baseline_lookup()
    comparisons = compare_to_r5(rows, base)

    core_comparisons = [x for x in comparisons]
    direction_all = all(x["direction_match"] for x in core_comparisons)
    p05_all = all(x["p05_classification_match"] for x in core_comparisons)

    env = {
        "python": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": {
            "pandas": version("pandas"),
            "linearmodels": version("linearmodels"),
            "numpy": version("numpy"),
            "scipy": version("scipy"),
            "statsmodels": version("statsmodels"),
        },
        "data24_sha256": sha256_file(DATA24),
        "data36_sha256": sha256_file(DATA36),
    }

    out = {
        "protocol": "OMOSSP_R6B_PYTHON_FORMAL_ROBUSTNESS_R1",
        "status": "FORMAL_R6B_PYTHON_ROBUSTNESS_FROZEN_PENDING_STATA17_VERIFICATION",
        "transparency": "R6 design frozen after R5 baseline results but before any R6 robustness outcomes.",
        "interpretation": "ASSOCIATIONAL_MEASUREMENT_VALIDATION_ONLY__NO_CAUSAL_CLAIM",
        "estimator": {
            "software": "Python linearmodels 6.1",
            "class": "PanelOLS",
            "entity_effects": True,
            "time_effects": True,
            "cov_type": "clustered",
            "cluster_entity": True,
            "debiased": True,
        },
        "all_frozen_core_specs_reported": True,
        "r6_1_ge18_regression_run": False,
        "r6_1_ge18_reason": "Descriptive sample diagnostic only because Model A has 465 projects < frozen N_min=500.",
        "md1_optional_aux_handling": "Both base and auxiliary MD1 specifications were run prospectively; neither can be selectively omitted based on results.",
        "specifications": specs,
        "comparison_to_r5": {
            "hard_magnitude_threshold": None,
            "significance_only_decision_prohibited": True,
            "all_common_slope_directions_match": direction_all,
            "all_common_slope_p05_classifications_match": p05_all,
            "comparison_row_count": len(core_comparisons),
            "evaluation_rule": "Report direction, magnitude change, uncertainty, and interpretation boundaries for all frozen specifications. Instability is a boundary condition, not a redesign trigger.",
        },
        "secondary_md1_samples": md1_samples,
        "next_gate": "STATA17_INDEPENDENT_ROBUSTNESS_VERIFICATION_REQUIRED_BEFORE_R6_CLOSEOUT",
    }

    pd.DataFrame(rows).to_csv(OUT_COEFF, index=False)
    pd.DataFrame(comparisons).to_csv(OUT_COMPARE, index=False)
    OUT_SUMMARY.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_ENV.write_text(json.dumps(env, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("===== OMOSSP_R6B_PYTHON_FORMAL_BEGIN =====")
    print(json.dumps(out, sort_keys=True))
    print("===== OMOSSP_R6B_PYTHON_FORMAL_END =====")
    print("R6B_PYTHON_FORMAL_COMPLETE")


if __name__ == "__main__":
    main()
