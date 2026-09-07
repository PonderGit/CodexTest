#!/usr/bin/env python3
import json
from pathlib import Path
import pandas as pd
from linearmodels.panel import PanelOLS

DATA=Path("data/r4_corrected/r4_corrected_project_month_panel.dta")
OUTDIR=Path("results/r5_preflight")
OUTDIR.mkdir(parents=True,exist_ok=True)
OUT_JSON=OUTDIR/"r5_panelols_preflight_summary.json"
OUT_CSV=OUTDIR/"r5_panelols_preflight_coefficients.csv"

MODELS={
  "A":{"y":"ln_open_age","x":["ln_resolution","ln_issues_new","ln_contributors"],"elig":"elig_A","expected_N":13808,"expected_projects":805},
  "B":{"y":"asinh_backlog","x":["ln_resolution","ln_issues_new","ln_contributors"],"elig":"elig_B","expected_N":13825,"expected_projects":805},
  "C":{"y":"ln_resolution","x":["ln_issues_new","ln_contributors"],"elig":"elig_C","expected_N":13825,"expected_projects":805},
  "D":{"y":"ln_open_age","x":["ln_issues_new","ln_contributors"],"elig":"elig_D","expected_N":20852,"expected_projects":871},
}

def fit_model(df,name,spec):
    # Match formal Stata rule: only projects with >=2 eligible months.
    g=df.groupby("project_id")[spec["elig"]].sum()
    keep=set(g[g>=2].index)
    sub=df[df["project_id"].isin(keep) & (df[spec["elig"]]==1)].copy()
    assert len(sub)==spec["expected_N"], (name,len(sub),spec["expected_N"])
    assert sub["project_id"].nunique()==spec["expected_projects"], (name,sub["project_id"].nunique(),spec["expected_projects"])

    sub=sub.set_index(["project_id","month_id"]).sort_index()
    y=sub[spec["y"]]
    X=sub[spec["x"]]
    mod=PanelOLS(y,X,entity_effects=True,time_effects=True,drop_absorbed=True,check_rank=True)
    res=mod.fit(cov_type="clustered",cluster_entity=True,debiased=True)

    coeff=[]
    for term in spec["x"]:
        coeff.append({
          "model":name,
          "term":term,
          "b":float(res.params[term]),
          "se":float(res.std_errors[term]),
          "t":float(res.tstats[term]),
          "p":float(res.pvalues[term]),
        })
    return {
      "model":name,
      "N":int(res.nobs),
      "projects":int(spec["expected_projects"]),
      "rsquared_within":float(res.rsquared_within),
      "rsquared_overall":float(res.rsquared_overall),
      "rsquared_between":float(res.rsquared_between),
      "coefficients":coeff
    }

def main():
    df=pd.read_stata(DATA,convert_categoricals=False)
    assert len(df)==21168
    assert df["project_id"].nunique()==882
    assert not df.duplicated(["project_id","month_id"]).any()

    out={"protocol":"OMOSSP_R5_NONFORMAL_PANELOLS_PREFLIGHT_R1",
         "formal_result_status":"NOT_FORMAL__MUST_BE_CONFIRMED_BY_STATA_LOG",
         "data_path":str(DATA),
         "models":{}}
    rows=[]
    for name,spec in MODELS.items():
        r=fit_model(df,name,spec)
        out["models"][name]={k:v for k,v in r.items() if k!="coefficients"}
        out["models"][name]["coefficients"]=r["coefficients"]
        rows.extend(r["coefficients"])

    OUT_JSON.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT_CSV,index=False)
    print("===== OMOSSP_R5_PREFLIGHT_BEGIN =====")
    print(json.dumps(out,sort_keys=True))
    print("===== OMOSSP_R5_PREFLIGHT_END =====")

if __name__=="__main__":
    main()
