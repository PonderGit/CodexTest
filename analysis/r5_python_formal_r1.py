#!/usr/bin/env python3
import hashlib
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

import pandas as pd
from linearmodels.panel import PanelOLS

DATA = Path("data/r4_corrected/r4_corrected_project_month_panel.dta")
OUTDIR = Path("results/r5_python_formal")
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUTDIR / "r5_python_formal_summary.json"
OUT_CSV = OUTDIR / "r5_python_formal_coefficients.csv"
OUT_ENV = OUTDIR / "r5_python_formal_environment.json"

EXPECTED_SHA256 = "814eef9868630ac94c0d59f15733b894c39dff78785a81f535cbcbf0f00c8346"

MODELS = {
    "A": {"y": "ln_open_age", "x": ["ln_resolution", "ln_issues_new", "ln_contributors"], "elig": "elig_A", "expected_N": 13781, "expected_projects": 805},
    "B": {"y": "asinh_backlog", "x": ["ln_resolution", "ln_issues_new", "ln_contributors"], "elig": "elig_B", "expected_N": 13797, "expected_projects": 805},
    "C": {"y": "ln_resolution", "x": ["ln_issues_new", "ln_contributors"], "elig": "elig_C", "expected_N": 13797, "expected_projects": 805},
    "D": {"y": "ln_open_age", "x": ["ln_issues_new", "ln_contributors"], "elig": "elig_D", "expected_N": 20852, "expected_projects": 871},
}

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def fit_model(df, name, spec):
    g = df.groupby("project_id")[spec["elig"]].sum()
    keep = set(g[g >= 2].index)
    sub = df[df["project_id"].isin(keep) & (df[spec["elig"]] == 1)].copy()
    assert len(sub) == spec["expected_N"], (name, len(sub), spec["expected_N"])
    assert sub["project_id"].nunique() == spec["expected_projects"], (name, sub["project_id"].nunique(), spec["expected_projects"])

    sub = sub.set_index(["project_id", "month_id"]).sort_index()
    y = sub[spec["y"]]
    X = sub[spec["x"]]

    mod = PanelOLS(
        y,
        X,
        entity_effects=True,
        time_effects=True,
        drop_absorbed=True,
        check_rank=True,
    )
    res = mod.fit(
        cov_type="clustered",
        cluster_entity=True,
        debiased=True,
    )

    coeff = []
    for term in spec["x"]:
        coeff.append({
            "model": name,
            "term": term,
            "b": float(res.params[term]),
            "se": float(res.std_errors[term]),
            "t": float(res.tstats[term]),
            "p": float(res.pvalues[term]),
        })
    return {
        "model": name,
        "N": int(res.nobs),
        "projects": int(spec["expected_projects"]),
        "rsquared_within": float(res.rsquared_within),
        "rsquared_overall": float(res.rsquared_overall),
        "rsquared_between": float(res.rsquared_between),
        "coefficients": coeff,
    }

def main():
    data_sha = sha256_file(DATA)
    assert data_sha == EXPECTED_SHA256, (data_sha, EXPECTED_SHA256)

    df = pd.read_stata(DATA, convert_categoricals=False)
    assert len(df) == 21168
    assert df["project_id"].nunique() == 882
    assert not df.duplicated(["project_id", "month_id"]).any()

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
        "data_sha256": data_sha,
        "data_path": str(DATA),
    }

    out = {
        "protocol": "OMOSSP_R5_PYTHON_FORMAL_PRIMARY_R1",
        "formal_result_status": "FORMAL_PYTHON_PRIMARY_FROZEN_PENDING_STATA17_VERIFICATION",
        "interpretation": "ASSOCIATIONAL_MEASUREMENT_VALIDATION_ONLY__NO_CAUSAL_CLAIM",
        "data_path": str(DATA),
        "data_sha256": data_sha,
        "estimator": {
            "software": "Python linearmodels",
            "class": "PanelOLS",
            "entity_effects": True,
            "time_effects": True,
            "cov_type": "clustered",
            "cluster_entity": True,
            "debiased": True,
        },
        "models": {},
    }
    rows = []
    for name, spec in MODELS.items():
        r = fit_model(df, name, spec)
        out["models"][name] = r
        rows.extend(r["coefficients"])

    OUT_JSON.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
    OUT_ENV.write_text(json.dumps(env, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("===== OMOSSP_R5_PYTHON_FORMAL_BEGIN =====")
    print(json.dumps(out, sort_keys=True))
    print("===== OMOSSP_R5_PYTHON_FORMAL_END =====")

if __name__ == "__main__":
    main()
