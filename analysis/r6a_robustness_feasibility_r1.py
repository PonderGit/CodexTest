#!/usr/bin/env python3
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

PRIMARY_DTA = Path("data/r4_corrected/r4_corrected_project_month_panel.dta")
RAW_GZ = Path("data/r4/r4_opendigger_raw_snapshot.jsonl.gz")
FRAME36 = Path("governance/r6_full36_structural_frame_r1.csv")
DESIGN = Path("governance/omossp_r6_robustness_design_lock_r1.json")

OUTDIR = Path("data/r6_36m")
GOV = Path("governance")
PANEL36_CSV = OUTDIR / "r6_36m_corrected_project_month_panel.csv"
PANEL36_DTA = OUTDIR / "r6_36m_corrected_project_month_panel.dta"
SUMMARY = GOV / "r6a_robustness_feasibility_summary_r1.json"
MANIFEST = GOV / "r6a_robustness_feasibility_manifest_r1.json"

EXPECTED_PRIMARY_DTA_SHA256 = "814eef9868630ac94c0d59f15733b894c39dff78785a81f535cbcbf0f00c8346"
EXPECTED_RAW_SHA256 = "ea2ffd5f86cfdd3d1681838521f74697754bce01854c0b78d4408c3fcbb8cf98"
EXPECTED_FRAME36_PROJECTS = 844
EXPECTED_FRAME36_BLOB = "18579662a20587e43a0b23d6dcf0f0e0a0b6276a"
MONTHS36 = [f"{y:04d}-{m:02d}" for y in (2023, 2024, 2025) for m in range(1, 13)]
METRICS = [
    "issue_resolution_duration",
    "issue_age",
    "issues_new",
    "contributors",
    "code_change_lines_sum",
]

MODELS = {
    "A": {"elig": "elig_A"},
    "B": {"elig": "elig_B"},
    "C": {"elig": "elig_C"},
    "D": {"elig": "elig_D"},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def finite_num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if math.isfinite(x) else None
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() in ("nan", "null", "none", "inf", "-inf", "infinity", "-infinity"):
            return None
        try:
            x = float(s)
            return x if math.isfinite(x) else None
        except ValueError:
            return None
    return None


def nested_month(obj, field, month):
    if not isinstance(obj, dict):
        return None
    node = obj.get(field)
    return node.get(month) if isinstance(node, dict) else None


def top_month(obj, month):
    return obj.get(month) if isinstance(obj, dict) else None


def levels_count(v):
    if not isinstance(v, list):
        return None
    vals = []
    for x in v:
        n = finite_num(x)
        if n is None:
            return None
        vals.append(n)
    total = sum(vals)
    return total if total >= 0 else None


def log1p_nonneg(x):
    return math.log1p(x) if x is not None and x >= 0 else None


def asinh_any(x):
    return math.asinh(x) if x is not None else None


def load_raw():
    out = {}
    with gzip.open(RAW_GZ, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            out[(r["repo_name"], r["metric"])] = r
    assert len(out) == 882 * 5, len(out)
    return out


def model_count_24m(df, elig, threshold):
    counts = df.groupby("project_id")[elig].sum()
    keep = counts[counts >= threshold].index
    sub = df[df["project_id"].isin(keep) & (df[elig] == 1)]
    return {"projects": int(len(keep)), "N": int(len(sub))}


def common_support_24m(df):
    vars_ = ["ln_resolution", "ln_open_age", "asinh_backlog", "ln_issues_new", "ln_contributors"]
    mask = df[vars_].notna().all(axis=1)
    counts = df.loc[mask].groupby("project_id").size()
    keep = counts[counts >= 2].index
    sub = df[mask & df["project_id"].isin(keep)]
    return {"projects": int(len(keep)), "N": int(len(sub))}


def build_36m(frame, raw):
    repos = list(frame["repo_name"])
    repo_to_pid = dict(zip(frame["repo_name"], frame["project_id"]))
    panel = []
    integrity = {
        "negative_resolution": 0,
        "negative_age": 0,
        "negative_backlog": 0,
        "negative_issues_new": 0,
        "negative_contributors": 0,
        "negative_net_code_lines_legitimate": 0,
        "resolution_q2_non_numeric": 0,
        "age_q2_non_numeric": 0,
        "invalid_age_levels": 0,
    }
    zero_fill = {
        "issues_new": 0,
        "contributors": 0,
        "backlog_count_from_missing_levels": 0,
        "net_code_lines_sparse_zero": 0,
    }
    status_counts = {m: {"200": 0, "404": 0, "ERROR": 0} for m in METRICS}

    for repo in repos:
        objs = {}
        statuses = {}
        for metric in METRICS:
            rec = raw[(repo, metric)]
            statuses[metric] = rec["status"]
            if rec["status"] == 200:
                status_counts[metric]["200"] += 1
            elif rec["status"] == 404:
                status_counts[metric]["404"] += 1
            else:
                status_counts[metric]["ERROR"] += 1
            objs[metric] = rec["payload"] if rec["status"] == 200 and isinstance(rec["payload"], dict) else None

        for month in MONTHS36:
            res_raw = nested_month(objs["issue_resolution_duration"], "quantile_2", month)
            age_raw = nested_month(objs["issue_age"], "quantile_2", month)
            levels_raw = nested_month(objs["issue_age"], "levels", month)

            res = finite_num(res_raw)
            age = finite_num(age_raw)
            backlog = levels_count(levels_raw)

            if res_raw is not None and res is None:
                integrity["resolution_q2_non_numeric"] += 1
            if age_raw is not None and age is None:
                integrity["age_q2_non_numeric"] += 1
            if isinstance(levels_raw, list) and backlog is None:
                integrity["invalid_age_levels"] += 1

            if res is not None and res < 0:
                integrity["negative_resolution"] += 1
                res = None
            if age is not None and age < 0:
                integrity["negative_age"] += 1
                age = None

            if statuses["issue_age"] == 200 and levels_raw is None:
                backlog = 0.0
                zero_fill["backlog_count_from_missing_levels"] += 1
            if backlog is not None and backlog < 0:
                integrity["negative_backlog"] += 1
                backlog = None

            def sparse_count(metric):
                if statuses[metric] != 200:
                    return None
                rawv = top_month(objs[metric], month)
                if rawv is None:
                    zero_fill[metric] += 1
                    return 0.0
                return finite_num(rawv)

            issues_new = sparse_count("issues_new")
            contributors = sparse_count("contributors")

            if issues_new is not None and issues_new < 0:
                integrity["negative_issues_new"] += 1
                issues_new = None
            if contributors is not None and contributors < 0:
                integrity["negative_contributors"] += 1
                contributors = None

            net_lines = None
            if statuses["code_change_lines_sum"] == 200:
                rawv = top_month(objs["code_change_lines_sum"], month)
                if rawv is None:
                    net_lines = 0.0
                    zero_fill["net_code_lines_sparse_zero"] += 1
                else:
                    net_lines = finite_num(rawv)
            if net_lines is not None and net_lines < 0:
                integrity["negative_net_code_lines_legitimate"] += 1

            row = {
                "project_id": repo_to_pid[repo],
                "repo_name": repo,
                "month": month,
                "res_med_days": res,
                "open_age_med_days": age,
                "open_backlog_n": backlog,
                "issues_new_n": issues_new,
                "contributors_n": contributors,
                "net_code_lines": net_lines,
                "ln_resolution": log1p_nonneg(res),
                "ln_open_age": log1p_nonneg(age),
                "asinh_backlog": asinh_any(backlog),
                "ln_issues_new": log1p_nonneg(issues_new),
                "ln_contributors": log1p_nonneg(contributors),
                "asinh_net_code_lines": asinh_any(net_lines),
            }
            context_ok = row["ln_issues_new"] is not None and row["ln_contributors"] is not None
            row["elig_A"] = int(context_ok and row["ln_resolution"] is not None and row["ln_open_age"] is not None)
            row["elig_B"] = int(context_ok and row["ln_resolution"] is not None and row["asinh_backlog"] is not None)
            row["elig_C"] = int(context_ok and row["ln_resolution"] is not None)
            row["elig_D"] = int(context_ok and row["ln_open_age"] is not None)
            panel.append(row)

    return panel, integrity, zero_fill, status_counts


def model_stats_panel(panel_df, flag):
    counts = panel_df.groupby("project_id")[flag].sum()
    out = {}
    for t in (1, 2, 6, 12, 18, 24):
        keep = counts[counts >= t].index
        n = len(panel_df[panel_df["project_id"].isin(keep) & (panel_df[flag] == 1)])
        out[f"projects_ge{t}"] = int(len(keep))
        out[f"N_ge{t}"] = int(n)
    return out


def main():
    assert DESIGN.exists()
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    assert design["status"] == "PASS__R6_ROBUSTNESS_DESIGN_FROZEN__NO_ROBUSTNESS_RESULTS_RUN"

    assert sha256_file(PRIMARY_DTA) == EXPECTED_PRIMARY_DTA_SHA256
    assert sha256_file(RAW_GZ) == EXPECTED_RAW_SHA256

    primary = pd.read_stata(PRIMARY_DTA, convert_categoricals=False)
    assert len(primary) == 21168
    assert primary["project_id"].nunique() == 882
    assert not primary.duplicated(["project_id", "month_id"]).any()

    robustness_24m = {
        "R6_1_minimum_usable_months": {
            model: {
                "ge6": model_count_24m(primary, spec["elig"], 6),
                "ge12": model_count_24m(primary, spec["elig"], 12),
                "ge18_descriptive_only": model_count_24m(primary, spec["elig"], 18),
            }
            for model, spec in MODELS.items()
        },
        "R6_2_common_support": common_support_24m(primary),
        "R6_3_auxiliary_signed_context": {},
    }

    assert robustness_24m["R6_1_minimum_usable_months"]["A"]["ge6"]["projects"] == 717
    assert robustness_24m["R6_1_minimum_usable_months"]["A"]["ge12"]["projects"] == 600
    assert robustness_24m["R6_1_minimum_usable_months"]["A"]["ge18_descriptive_only"]["projects"] == 465
    assert robustness_24m["R6_2_common_support"] == {"projects": 805, "N": 13781}

    for model, spec in MODELS.items():
        counts = primary.groupby("project_id")[spec["elig"]].sum()
        keep = counts[counts >= 2].index
        sub = primary[primary["project_id"].isin(keep) & (primary[spec["elig"]] == 1)]
        robustness_24m["R6_3_auxiliary_signed_context"][model] = {
            "baseline_projects": int(len(keep)),
            "baseline_N": int(len(sub)),
            "asinh_net_code_lines_missing_in_baseline_sample": int(sub["asinh_net_code_lines"].isna().sum()),
        }

    frame = pd.read_csv(FRAME36)
    assert len(frame) == EXPECTED_FRAME36_PROJECTS
    assert frame["project_id"].nunique() == EXPECTED_FRAME36_PROJECTS
    assert frame["repo_name"].nunique() == EXPECTED_FRAME36_PROJECTS
    assert (frame["full_exposure_36"] == 1).all()

    raw = load_raw()
    panel36, integrity, zero_fill, status_counts = build_36m(frame, raw)
    assert len(panel36) == EXPECTED_FRAME36_PROJECTS * 36

    OUTDIR.mkdir(parents=True, exist_ok=True)
    df36 = pd.DataFrame(panel36)
    assert not df36.duplicated(["project_id", "month"]).any()
    df36["month_id"] = pd.PeriodIndex(df36["month"], freq="M").astype("int64")
    df36.to_csv(PANEL36_CSV, index=False)
    df36.to_stata(PANEL36_DTA, write_index=False, version=118)

    eligibility36 = {m: model_stats_panel(df36, spec["elig"]) for m, spec in MODELS.items()}
    feasibility_gate = eligibility36["A"]["projects_ge2"] >= 500

    variable_missingness = {}
    for v in ["res_med_days", "open_age_med_days", "open_backlog_n", "issues_new_n", "contributors_n", "net_code_lines"]:
        n = int(df36[v].isna().sum())
        variable_missingness[v] = {
            "missing": n,
            "observed": int(len(df36) - n),
            "missing_rate": n / len(df36),
        }

    summary = {
        "protocol": "OMOSSP_R6A_ROBUSTNESS_IMPLEMENTATION_36M_FEASIBILITY_R1",
        "date": "2026-09-07",
        "status": "PASS__R6A_IMPLEMENTATION_AND_FEASIBILITY_COMPLETE__NO_ROBUSTNESS_REGRESSION_RUN",
        "regression_run": False,
        "robustness_coefficients_computed": False,
        "robustness_standard_errors_computed": False,
        "robustness_pvalues_computed": False,
        "primary_24m_input_sha256": sha256_file(PRIMARY_DTA),
        "raw_snapshot_sha256": sha256_file(RAW_GZ),
        "frame36_projects": int(len(frame)),
        "panel36_months": 36,
        "panel36_rows": int(len(df36)),
        "robustness_24m_sample_identity": robustness_24m,
        "panel36_integrity": integrity,
        "panel36_zero_fill_counts": zero_fill,
        "panel36_file_status": status_counts,
        "panel36_variable_missingness": variable_missingness,
        "panel36_model_eligibility": eligibility36,
        "model_A_ge2_projects": eligibility36["A"]["projects_ge2"],
        "formal_36m_regression_feasibility_gate_min_projects": 500,
        "formal_36m_regression_feasible": bool(feasibility_gate),
        "formal_36m_regression_authorization": "AUTHORIZED_NEXT_STAGE" if feasibility_gate else "NOT_ESTIMABLE_UNDER_FROZEN_DESIGN",
        "interpretation": "SAMPLE_AND_DATA_FEASIBILITY_ONLY__NO_ROBUSTNESS_RESULT_INTERPRETATION",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "protocol": "OMOSSP_R6A_ROBUSTNESS_FEASIBILITY_MANIFEST_R1",
        "inputs": {
            str(PRIMARY_DTA): sha256_file(PRIMARY_DTA),
            str(RAW_GZ): sha256_file(RAW_GZ),
            str(FRAME36): {"projects": len(frame), "git_blob_expected": EXPECTED_FRAME36_BLOB},
            str(DESIGN): sha256_file(DESIGN),
        },
        "outputs": {
            str(PANEL36_CSV): {"bytes": PANEL36_CSV.stat().st_size, "sha256": sha256_file(PANEL36_CSV)},
            str(PANEL36_DTA): {"bytes": PANEL36_DTA.stat().st_size, "sha256": sha256_file(PANEL36_DTA)},
            str(SUMMARY): {"bytes": SUMMARY.stat().st_size, "sha256": sha256_file(SUMMARY)},
        },
        "regression_run": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("===== OMOSSP_R6A_FEASIBILITY_BEGIN =====")
    print(json.dumps(summary, sort_keys=True))
    print("===== OMOSSP_R6A_FEASIBILITY_END =====")
    print("R6A_36M_PANEL_CSV_SHA256=" + sha256_file(PANEL36_CSV))
    print("R6A_36M_PANEL_DTA_SHA256=" + sha256_file(PANEL36_DTA))
    print("R6A_NO_ROBUSTNESS_REGRESSION_RUN=PASS")


if __name__ == "__main__":
    main()
