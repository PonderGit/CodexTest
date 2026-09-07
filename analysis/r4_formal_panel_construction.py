#!/usr/bin/env python3
import csv, gzip, hashlib, json, math, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

FRAME=Path("governance/r3_formal_github_project_frame_r1.csv")
OUTDIR=Path("data/r4")
GOV=Path("governance")
RAW_GZ=OUTDIR/"r4_opendigger_raw_snapshot.jsonl.gz"
LEDGER=OUTDIR/"r4_retrieval_ledger.csv"
PANEL_CSV=OUTDIR/"r4_project_month_panel.csv"
PANEL_DTA=OUTDIR/"r4_project_month_panel.dta"
DICT_JSON=GOV/"r4_variable_dictionary_r1.json"
SUMMARY_JSON=GOV/"r4_panel_data_quality_summary_r1.json"
MANIFEST_JSON=GOV/"r4_panel_manifest_r1.json"

BASE="https://oss.open-digger.cn/github"
UA="OMOSSP-R4-formal-panel/1.0"
METRICS=[
  "issue_resolution_duration",
  "issue_age",
  "issues_new",
  "contributors",
  "code_change_lines_sum",
]
MONTHS=[f"{y:04d}-{m:02d}" for y,m in [(2024,m) for m in range(1,13)]+[(2025,m) for m in range(1,13)]]
OD_HEAD="63e4b89ecd525221be95fe2a48a714ebb3c722ec"
CHAOSS_BLOB="b7a9293434a081d713406eac5f7fc889d35de97f"
BASIC_BLOB="741591d9916ae068c0c5b46d6fe7e24b025a43bc"

def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()

def sha256_file(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def fetch_bytes(url, attempts=4, timeout=30):
    last=None
    for i in range(attempts):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                raw=r.read()
                return {"status":int(r.status),"raw":raw,"error":""}
        except urllib.error.HTTPError as e:
            if e.code==404:
                return {"status":404,"raw":b"","error":""}
            last=f"HTTP_{e.code}"
            if e.code not in (429,500,502,503,504): break
        except Exception as e:
            last=type(e).__name__
        time.sleep(0.5*(2**i))
    return {"status":"ERROR","raw":b"","error":last or "UNKNOWN"}

def url_for(repo,metric):
    owner,name=repo.split("/",1)
    return f"{BASE}/{quote(owner,safe='')}/{quote(name,safe='')}/{metric}.json"

def load_frame():
    rows=[]
    with FRAME.open(newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    assert len(rows)==882, f"Expected 882 frame projects, got {len(rows)}"
    assert len({r["project_id"] for r in rows})==882
    assert len({r["repo_name"].casefold() for r in rows})==882
    return rows

def finite_num(v):
    if isinstance(v,bool) or v is None: return None
    if isinstance(v,(int,float)):
        return float(v) if math.isfinite(float(v)) else None
    if isinstance(v,str):
        s=v.strip()
        if not s or s.lower() in ("nan","null","none","inf","-inf","infinity","-infinity"): return None
        try:
            x=float(s)
            return x if math.isfinite(x) else None
        except: return None
    return None

def nested_month(obj,field,month):
    if not isinstance(obj,dict): return None
    node=obj.get(field)
    if not isinstance(node,dict): return None
    return node.get(month)

def top_month(obj,month):
    if not isinstance(obj,dict): return None
    return obj.get(month)

def levels_count(v):
    if not isinstance(v,list): return None
    vals=[]
    for x in v:
        n=finite_num(x)
        if n is None: return None
        vals.append(n)
    total=sum(vals)
    if total < 0: return None
    return total

def safe_log1p(x):
    if x is None or x < 0: return None
    return math.log1p(x)

def safe_asinh(x):
    if x is None: return None
    return math.asinh(x)

def compact_payload(raw):
    if not raw: return None
    try: return json.loads(raw.decode("utf-8"))
    except: return None

def retrieve_one(repo,metric):
    url=url_for(repo,metric)
    x=fetch_bytes(url)
    payload=compact_payload(x["raw"]) if x["status"]==200 else None
    parse_ok=int(x["status"]!=200 or isinstance(payload,dict))
    return {
      "repo_name":repo,"metric":metric,"url":url,
      "status":x["status"],"error":x["error"],
      "bytes":len(x["raw"]),"sha256":sha256_bytes(x["raw"]) if x["raw"] else "",
      "parse_ok":parse_ok,"payload":payload
    }

def main():
    OUTDIR.mkdir(parents=True,exist_ok=True); GOV.mkdir(parents=True,exist_ok=True)
    frame=load_frame()
    repo_to_pid={r["repo_name"]:r["project_id"] for r in frame}
    repos=sorted(repo_to_pid,key=str.casefold)

    fetched={}
    jobs=[]
    with ThreadPoolExecutor(max_workers=28) as ex:
        for repo in repos:
            for metric in METRICS:
                jobs.append(ex.submit(retrieve_one,repo,metric))
        for i,f in enumerate(as_completed(jobs),1):
            r=f.result()
            fetched[(r["repo_name"],r["metric"])]=r
            if i%250==0:
                print(f"R4_RETRIEVAL_PROGRESS={i}/{len(jobs)}",flush=True)

    # Deterministic raw snapshot; payloads retained exactly as parsed JSON plus byte hash/URL.
    raw_lines=[]
    ledger_rows=[]
    for repo in repos:
        for metric in METRICS:
            r=fetched[(repo,metric)]
            rec={
              "repo_name":repo,"metric":metric,"url":r["url"],
              "status":r["status"],"error":r["error"],"bytes":r["bytes"],
              "sha256":r["sha256"],"parse_ok":r["parse_ok"],
              "payload":r["payload"]
            }
            raw_lines.append(json.dumps(rec,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n")
            ledger_rows.append({k:r[k] for k in ["repo_name","metric","url","status","error","bytes","sha256","parse_ok"]})

    with open(RAW_GZ,"wb") as rawf:
        with gzip.GzipFile(filename="",mode="wb",fileobj=rawf,mtime=0) as gz:
            for line in raw_lines:
                gz.write(line.encode("utf-8"))

    with LEDGER.open("w",newline="",encoding="utf-8") as f:
        fields=["repo_name","metric","url","status","error","bytes","sha256","parse_ok"]
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(ledger_rows)

    # Build 882 x 24 skeleton.
    panel=[]
    integrity={
      "negative_resolution":0,"negative_age":0,"negative_issues_new":0,
      "negative_contributors":0,"negative_code_lines":0,
      "invalid_age_levels":0,"resolution_q2_non_numeric":0,"age_q2_non_numeric":0
    }
    zero_fill={"issues_new":0,"contributors":0,"code_change_lines_sum":0,"backlog_count_from_missing_levels":0}
    missing_files={m:0 for m in METRICS}
    for repo in repos:
        pid=repo_to_pid[repo]
        objs={}
        statuses={}
        for metric in METRICS:
            fr=fetched[(repo,metric)]
            statuses[metric]=fr["status"]
            objs[metric]=fr["payload"] if fr["status"]==200 and isinstance(fr["payload"],dict) else None
            if fr["status"]!=200: missing_files[metric]+=1

        for month in MONTHS:
            res_raw=nested_month(objs["issue_resolution_duration"],"quantile_2",month)
            age_raw=nested_month(objs["issue_age"],"quantile_2",month)
            levels_raw=nested_month(objs["issue_age"],"levels",month)

            res=finite_num(res_raw)
            age=finite_num(age_raw)
            backlog=levels_count(levels_raw)

            if res_raw is not None and res is None: integrity["resolution_q2_non_numeric"]+=1
            if age_raw is not None and age is None: integrity["age_q2_non_numeric"]+=1
            if isinstance(levels_raw,list) and backlog is None: integrity["invalid_age_levels"]+=1

            # issue_age implementation defaults the month-end age-level vector to zero counts.
            # Static sparse omission is therefore treated as zero backlog only when the issue_age
            # file itself is successfully observed for the repository.
            if statuses["issue_age"]==200 and levels_raw is None:
                backlog=0.0
                zero_fill["backlog_count_from_missing_levels"]+=1

            def count_metric(metric):
                if statuses[metric]!=200: return None
                raw=top_month(objs[metric],month)
                if raw is None:
                    zero_fill[metric]+=1
                    return 0.0
                return finite_num(raw)

            issues_new=count_metric("issues_new")
            contributors=count_metric("contributors")
            code_lines=count_metric("code_change_lines_sum")

            if res is not None and res<0: integrity["negative_resolution"]+=1; res=None
            if age is not None and age<0: integrity["negative_age"]+=1; age=None
            if issues_new is not None and issues_new<0: integrity["negative_issues_new"]+=1; issues_new=None
            if contributors is not None and contributors<0: integrity["negative_contributors"]+=1; contributors=None
            if code_lines is not None and code_lines<0: integrity["negative_code_lines"]+=1; code_lines=None

            row={
              "project_id":pid,"repo_name":repo,"month":month,
              "res_med_days":res,
              "open_age_med_days":age,
              "open_backlog_n":backlog,
              "issues_new_n":issues_new,
              "contributors_n":contributors,
              "code_lines_n":code_lines,
              "ln_resolution":safe_log1p(res),
              "ln_open_age":safe_log1p(age),
              "asinh_backlog":safe_asinh(backlog),
              "ln_issues_new":safe_log1p(issues_new),
              "ln_contributors":safe_log1p(contributors),
              "ln_code_lines":safe_log1p(code_lines),
            }
            context_ok=all(row[k] is not None for k in ["ln_issues_new","ln_contributors","ln_code_lines"])
            row["elig_A"]=int(context_ok and row["ln_resolution"] is not None and row["ln_open_age"] is not None)
            row["elig_B"]=int(context_ok and row["ln_resolution"] is not None and row["asinh_backlog"] is not None)
            row["elig_C"]=int(context_ok and row["ln_resolution"] is not None)
            row["elig_D"]=int(context_ok and row["ln_open_age"] is not None)
            panel.append(row)

    assert len(panel)==882*24

    # CSV output.
    fields=list(panel[0].keys())
    with PANEL_CSV.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in panel: w.writerow(r)

    # Stata export.
    import pandas as pd
    df=pd.DataFrame(panel)
    df["month_id"]=pd.PeriodIndex(df["month"],freq="M").astype("int64")
    # Stata variable names are <=32 chars already.
    df.to_stata(PANEL_DTA,write_index=False,version=118)

    def project_counts(flag):
        by={}
        for r in panel:
            if r[flag]:
                by[r["project_id"]]=by.get(r["project_id"],0)+1
        return {
          "projects_ge1":sum(v>=1 for v in by.values()),
          "projects_ge2":sum(v>=2 for v in by.values()),
          "projects_ge6":sum(v>=6 for v in by.values()),
          "projects_ge12":sum(v>=12 for v in by.values()),
          "projects_ge18":sum(v>=18 for v in by.values()),
          "project_month_NT":sum(by.values())
        }

    variable_missing={}
    numeric_vars=["res_med_days","open_age_med_days","open_backlog_n","issues_new_n","contributors_n","code_lines_n"]
    for v in numeric_vars:
        nmiss=sum(r[v] is None for r in panel)
        variable_missing[v]={"missing":nmiss,"observed":len(panel)-nmiss,"missing_rate":round(nmiss/len(panel),6)}

    variable_dictionary={
      "protocol":"OMOSSP_R4_VARIABLE_DICTIONARY_R1",
      "unit":"project-month",
      "platform":"GitHub",
      "window":"2024-01..2025-12",
      "variables":{
        "res_med_days":{"source":"issue_resolution_duration.quantile_2","construct_role":"candidate completed-item timeliness","zero_rule":"never zero-fill; undefined when no estimable closed-item median"},
        "open_age_med_days":{"source":"issue_age.quantile_2","construct_role":"unresolved-backlog age evidence","zero_rule":"undefined when no open-age distribution"},
        "open_backlog_n":{"source":"sum(issue_age.levels)","construct_role":"unresolved backlog burden/context","zero_rule":"zero when issue_age is observed and month levels are omitted under the locked sparse/default semantics"},
        "issues_new_n":{"source":"issues_new[month]","construct_role":"incoming observable workload context","zero_rule":"zero-fill omitted month within verified source observability"},
        "contributors_n":{"source":"contributors[month]","construct_role":"participation-breadth context","zero_rule":"zero-fill omitted month within verified source observability"},
        "code_lines_n":{"source":"code_change_lines_sum[month]","construct_role":"code-change magnitude/activity context","zero_rule":"zero-fill omitted month within verified source observability"},
        "ln_resolution":{"formula":"ln(1 + res_med_days)"},
        "ln_open_age":{"formula":"ln(1 + open_age_med_days)"},
        "asinh_backlog":{"formula":"asinh(open_backlog_n)"},
        "ln_issues_new":{"formula":"ln(1 + issues_new_n)"},
        "ln_contributors":{"formula":"ln(1 + contributors_n)"},
        "ln_code_lines":{"formula":"ln(1 + code_lines_n)"}
      },
      "source_version":{"opendigger_master_head":OD_HEAD,"chaoss_ts_blob":CHAOSS_BLOB,"basic_ts_blob":BASIC_BLOB}
    }
    DICT_JSON.write_text(json.dumps(variable_dictionary,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    summary={
      "protocol":"OMOSSP_R4_FORMAL_PANEL_DATA_QUALITY_R1",
      "frame_projects":882,
      "months":24,
      "skeleton_project_months":len(panel),
      "retrieval_files":len(ledger_rows),
      "retrieval_status_counts":{},
      "missing_files_by_metric":missing_files,
      "zero_fill_counts":zero_fill,
      "integrity_checks":integrity,
      "variable_missingness":variable_missing,
      "model_eligibility":{
        "A":project_counts("elig_A"),
        "B":project_counts("elig_B"),
        "C":project_counts("elig_C"),
        "D":project_counts("elig_D")
      },
      "sample_floor_projects":500,
      "preferred_projects":750,
      "selection_integrity":{
        "new_variables_added":False,
        "performance_value_based_project_exclusion":False,
        "formal_regression_run":False
      }
    }
    for r in ledger_rows:
        k=str(r["status"])
        summary["retrieval_status_counts"][k]=summary["retrieval_status_counts"].get(k,0)+1
    SUMMARY_JSON.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    manifest={
      "protocol":"OMOSSP_R4_PANEL_MANIFEST_R1",
      "inputs":{
        "formal_frame_path":str(FRAME),
        "formal_frame_sha256":sha256_file(FRAME),
        "opendigger_master_head":OD_HEAD,
        "chaoss_ts_blob":CHAOSS_BLOB,
        "basic_ts_blob":BASIC_BLOB
      },
      "outputs":{}
    }
    for p in [RAW_GZ,LEDGER,PANEL_CSV,PANEL_DTA,DICT_JSON,SUMMARY_JSON]:
        manifest["outputs"][str(p)]={"bytes":p.stat().st_size,"sha256":sha256_file(p)}
    MANIFEST_JSON.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest["outputs"][str(MANIFEST_JSON)]={"bytes":MANIFEST_JSON.stat().st_size,"sha256":sha256_file(MANIFEST_JSON)}
    MANIFEST_JSON.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    print("===== OMOSSP_R4_SUMMARY_BEGIN =====")
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    print("===== OMOSSP_R4_SUMMARY_END =====")
    print("R4_RAW_SHA256="+sha256_file(RAW_GZ))
    print("R4_PANEL_CSV_SHA256="+sha256_file(PANEL_CSV))
    print("R4_PANEL_DTA_SHA256="+sha256_file(PANEL_DTA))

if __name__=="__main__":
    main()
