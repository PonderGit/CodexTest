#!/usr/bin/env python3
import csv, gzip, hashlib, json, math
from pathlib import Path

FRAME=Path("governance/r3_formal_github_project_frame_r1.csv")
RAW_GZ=Path("data/r4/r4_opendigger_raw_snapshot.jsonl.gz")
OUTDIR=Path("data/r4_corrected")
GOV=Path("governance")
PANEL_CSV=OUTDIR/"r4_corrected_project_month_panel.csv"
PANEL_DTA=OUTDIR/"r4_corrected_project_month_panel.dta"
DICT_JSON=GOV/"r4_corrected_variable_dictionary_r1.json"
SUMMARY_JSON=GOV/"r4_corrected_panel_data_quality_summary_r1.json"
MANIFEST_JSON=GOV/"r4_corrected_panel_manifest_r1.json"

MONTHS=[f"{y:04d}-{m:02d}" for y,m in [(2024,m) for m in range(1,13)]+[(2025,m) for m in range(1,13)]]

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()

def finite_num(v):
    if isinstance(v,bool) or v is None: return None
    if isinstance(v,(int,float)):
        x=float(v); return x if math.isfinite(x) else None
    if isinstance(v,str):
        s=v.strip()
        if not s or s.lower() in ("nan","null","none","inf","-inf","infinity","-infinity"): return None
        try:
            x=float(s); return x if math.isfinite(x) else None
        except: return None
    return None

def nested_month(obj,field,month):
    if not isinstance(obj,dict): return None
    node=obj.get(field)
    return node.get(month) if isinstance(node,dict) else None

def top_month(obj,month):
    return obj.get(month) if isinstance(obj,dict) else None

def levels_count(v):
    if not isinstance(v,list): return None
    vals=[]
    for x in v:
        n=finite_num(x)
        if n is None: return None
        vals.append(n)
    total=sum(vals)
    return total if total>=0 else None

def log1p_nonneg(x):
    return math.log1p(x) if x is not None and x>=0 else None

def asinh_any(x):
    return math.asinh(x) if x is not None else None

def load_frame():
    rows=[]
    with FRAME.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==882
    return rows

def load_raw():
    out={}
    with gzip.open(RAW_GZ,"rt",encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            r=json.loads(line)
            out[(r["repo_name"],r["metric"])]=r
    assert len(out)==882*5
    return out

def main():
    OUTDIR.mkdir(parents=True,exist_ok=True)
    frame=load_frame()
    raw=load_raw()
    repo_to_pid={r["repo_name"]:r["project_id"] for r in frame}
    repos=sorted(repo_to_pid,key=str.casefold)
    panel=[]
    integrity={
      "negative_resolution":0,"negative_age":0,"negative_issues_new":0,
      "negative_contributors":0,"negative_backlog":0,
      "negative_net_code_lines_legitimate":0,
      "resolution_q2_non_numeric":0,"age_q2_non_numeric":0,"invalid_age_levels":0
    }
    zero_fill={"issues_new":0,"contributors":0,"backlog_count_from_missing_levels":0,"net_code_lines_sparse_zero":0}
    file_status={}
    for metric in ["issue_resolution_duration","issue_age","issues_new","contributors","code_change_lines_sum"]:
        file_status[metric]={"200":0,"404":0,"ERROR":0}
    for repo in repos:
        objs={}; statuses={}
        for metric in file_status:
            rec=raw[(repo,metric)]
            st=str(rec["status"])
            statuses[metric]=rec["status"]
            if st in file_status[metric]: file_status[metric][st]+=1
            elif rec["status"]==200: file_status[metric]["200"]+=1
            else: file_status[metric]["ERROR"]+=1
            objs[metric]=rec["payload"] if rec["status"]==200 and isinstance(rec["payload"],dict) else None

        for month in MONTHS:
            res_raw=nested_month(objs["issue_resolution_duration"],"quantile_2",month)
            age_raw=nested_month(objs["issue_age"],"quantile_2",month)
            levels_raw=nested_month(objs["issue_age"],"levels",month)
            res=finite_num(res_raw); age=finite_num(age_raw); backlog=levels_count(levels_raw)

            if res_raw is not None and res is None: integrity["resolution_q2_non_numeric"]+=1
            if age_raw is not None and age is None: integrity["age_q2_non_numeric"]+=1
            if isinstance(levels_raw,list) and backlog is None: integrity["invalid_age_levels"]+=1
            if res is not None and res<0: integrity["negative_resolution"]+=1; res=None
            if age is not None and age<0: integrity["negative_age"]+=1; age=None

            if statuses["issue_age"]==200 and levels_raw is None:
                backlog=0.0; zero_fill["backlog_count_from_missing_levels"]+=1
            if backlog is not None and backlog<0:
                integrity["negative_backlog"]+=1; backlog=None

            def sparse_count(metric):
                if statuses[metric]!=200: return None
                rawv=top_month(objs[metric],month)
                if rawv is None:
                    zero_fill[metric]+=1
                    return 0.0
                return finite_num(rawv)

            issues_new=sparse_count("issues_new")
            contributors=sparse_count("contributors")

            if issues_new is not None and issues_new<0:
                integrity["negative_issues_new"]+=1; issues_new=None
            if contributors is not None and contributors<0:
                integrity["negative_contributors"]+=1; contributors=None

            # OpenDigger code_change_lines_sum = additions - deletions.
            # Signed negatives are valid; sparse month inside observed file is 0 net change.
            net_lines=None
            if statuses["code_change_lines_sum"]==200:
                rawv=top_month(objs["code_change_lines_sum"],month)
                if rawv is None:
                    net_lines=0.0; zero_fill["net_code_lines_sparse_zero"]+=1
                else:
                    net_lines=finite_num(rawv)
            if net_lines is not None and net_lines<0:
                integrity["negative_net_code_lines_legitimate"]+=1

            row={
              "project_id":repo_to_pid[repo],"repo_name":repo,"month":month,
              "res_med_days":res,"open_age_med_days":age,"open_backlog_n":backlog,
              "issues_new_n":issues_new,"contributors_n":contributors,
              "net_code_lines":net_lines,
              "ln_resolution":log1p_nonneg(res),
              "ln_open_age":log1p_nonneg(age),
              "asinh_backlog":asinh_any(backlog),
              "ln_issues_new":log1p_nonneg(issues_new),
              "ln_contributors":log1p_nonneg(contributors),
              "asinh_net_code_lines":asinh_any(net_lines),
            }
            context_ok=row["ln_issues_new"] is not None and row["ln_contributors"] is not None
            row["elig_A"]=int(context_ok and row["ln_resolution"] is not None and row["ln_open_age"] is not None)
            row["elig_B"]=int(context_ok and row["ln_resolution"] is not None and row["asinh_backlog"] is not None)
            row["elig_C"]=int(context_ok and row["ln_resolution"] is not None)
            row["elig_D"]=int(context_ok and row["ln_open_age"] is not None)
            panel.append(row)

    assert len(panel)==882*24

    fields=list(panel[0].keys())
    with PANEL_CSV.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(panel)

    import pandas as pd
    df=pd.DataFrame(panel)
    df["month_id"]=pd.PeriodIndex(df["month"],freq="M").astype("int64")
    df.to_stata(PANEL_DTA,write_index=False,version=118)

    def model_stats(flag):
        by={}
        for r in panel:
            if r[flag]: by[r["project_id"]]=by.get(r["project_id"],0)+1
        return {
          "projects_ge1":sum(v>=1 for v in by.values()),
          "projects_ge2":sum(v>=2 for v in by.values()),
          "projects_ge6":sum(v>=6 for v in by.values()),
          "projects_ge12":sum(v>=12 for v in by.values()),
          "projects_ge18":sum(v>=18 for v in by.values()),
          "project_month_NT":sum(by.values())
        }

    vars_=["res_med_days","open_age_med_days","open_backlog_n","issues_new_n","contributors_n","net_code_lines"]
    miss={}
    for v in vars_:
        n=sum(r[v] is None for r in panel)
        miss[v]={"missing":n,"observed":len(panel)-n,"missing_rate":round(n/len(panel),6)}

    summary={
      "protocol":"OMOSSP_R4_CORRECTED_FORMAL_PANEL_DATA_QUALITY_R1",
      "frame_projects":882,"months":24,"skeleton_project_months":len(panel),
      "source_raw_snapshot_sha256":sha256_file(RAW_GZ),
      "file_status":file_status,
      "zero_fill_counts":zero_fill,
      "integrity_checks":integrity,
      "variable_missingness":miss,
      "model_eligibility":{"A":model_stats("elig_A"),"B":model_stats("elig_B"),"C":model_stats("elig_C"),"D":model_stats("elig_D")},
      "sample_floor_projects":500,"preferred_projects":750,
      "baseline_context_covariates":["ln_issues_new","ln_contributors"],
      "net_code_lines_status":"AUXILIARY_SIGNED_CONTEXT_ONLY__NOT_BASELINE",
      "formal_regression_run":False,
      "performance_value_based_project_exclusion":False
    }
    SUMMARY_JSON.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    dct={
      "protocol":"OMOSSP_R4_CORRECTED_VARIABLE_DICTIONARY_R1",
      "unit":"project-month","platform":"GitHub","window":"2024-01..2025-12",
      "baseline_models_use":["ln_resolution","ln_open_age","asinh_backlog","ln_issues_new","ln_contributors"],
      "variables":{
        "res_med_days":{"source":"issue_resolution_duration.quantile_2","role":"candidate completed-item timeliness","transform":"ln1p"},
        "open_age_med_days":{"source":"issue_age.quantile_2","role":"unresolved-backlog age evidence","transform":"ln1p"},
        "open_backlog_n":{"source":"sum(issue_age.levels)","role":"unresolved backlog burden","transform":"asinh"},
        "issues_new_n":{"source":"issues_new[month]","role":"incoming issue-volume context","transform":"ln1p"},
        "contributors_n":{"source":"contributors[month]","role":"participation-breadth context","transform":"ln1p"},
        "net_code_lines":{"source":"code_change_lines_sum[month]","role":"signed net code-size change only","transform":"asinh","baseline_status":"excluded"}
      },
      "semantic_correction":"OpenDigger code_change_lines_sum = additions - deletions. It is not total code-change magnitude."
    }
    DICT_JSON.write_text(json.dumps(dct,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    manifest={
      "protocol":"OMOSSP_R4_CORRECTED_PANEL_MANIFEST_R1",
      "inputs":{
        "formal_frame_sha256":sha256_file(FRAME),
        "raw_snapshot_sha256":sha256_file(RAW_GZ),
        "source_semantics_correction":"governance/omossp_r4_source_semantics_correction_addendum_r1.json"
      },
      "outputs":{}
    }
    for p in [PANEL_CSV,PANEL_DTA,DICT_JSON,SUMMARY_JSON]:
        manifest["outputs"][str(p)]={"bytes":p.stat().st_size,"sha256":sha256_file(p)}
    MANIFEST_JSON.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    print("===== OMOSSP_R4_CORRECTED_SUMMARY_BEGIN =====")
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    print("===== OMOSSP_R4_CORRECTED_SUMMARY_END =====")
    print("R4_CORRECTED_PANEL_CSV_SHA256="+sha256_file(PANEL_CSV))
    print("R4_CORRECTED_PANEL_DTA_SHA256="+sha256_file(PANEL_DTA))

if __name__=="__main__":
    main()
