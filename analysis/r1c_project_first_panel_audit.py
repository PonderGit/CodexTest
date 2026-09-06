#!/usr/bin/env python3
import csv, json, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median
from urllib.parse import quote

SNAPSHOT=Path("governance/r1b_oss_compass_gitee_single_repository_snapshot_20260906.csv")
OUT_SUMMARY=Path("governance/r1c_gitee_project_first_panel_coverage_summary.json")
OUT_REPO=Path("governance/r1c_gitee_project_first_panel_coverage_by_repo.csv")

BASE="https://oss.open-digger.cn/gitee"
UA="OMOSSP-R1C-coverage-audit/1.0"
METRICS=[
    "issues_new",
    "issues_closed",
    "issue_response_time",
    "issue_resolution_duration",
    "change_requests",
    "change_requests_accepted",
    "change_request_response_time",
    "change_request_resolution_duration",
    "contributors",
    "code_change_lines_sum",
]
COUNT_METRICS={
    "issues_new","issues_closed","change_requests","change_requests_accepted",
    "contributors","code_change_lines_sum"
}
DURATION_METRICS={
    "issue_response_time","issue_resolution_duration",
    "change_request_response_time","change_request_resolution_duration"
}
MONTH_RE=re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])$")
RAW_MONTH_RE=re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])-raw$")

def months(start,end):
    sy,sm=map(int,start.split("-")); ey,em=map(int,end.split("-"))
    out=[]; y,m=sy,sm
    while (y,m) <= (ey,em):
        out.append(f"{y:04d}-{m:02d}")
        m+=1
        if m==13: y+=1; m=1
    return out

W24=months("2024-01","2025-12")
W36=months("2023-01","2025-12")

def fetch_json(url, attempts=3, timeout=20):
    last=None
    for i in range(attempts):
        try:
            req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept":"application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw=r.read()
                return {"status":int(r.status),"json":json.loads(raw.decode("utf-8")),"bytes":len(raw)}
        except urllib.error.HTTPError as e:
            if e.code==404:
                return {"status":404,"json":None,"bytes":0}
            last=f"HTTP_{e.code}"
            if e.code not in (429,500,502,503,504): break
        except Exception as e:
            last=type(e).__name__
        time.sleep(0.5*(2**i))
    return {"status":"ERROR","json":None,"bytes":0,"error":last}

def repo_url(repo_name, leaf):
    owner, repo = repo_name.split("/",1)
    return f"{BASE}/{quote(owner,safe='')}/{quote(repo,safe='')}/{leaf}"

def key_profile(obj):
    mm=set(); rr=set()
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                ks=str(k)
                if MONTH_RE.match(ks): mm.add(ks)
                elif RAW_MONTH_RE.match(ks): rr.add(ks[:-4])
                walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(obj)
    return {"months":sorted(mm),"raw_months":sorted(rr)}

def load_candidates():
    dedup={}
    with SNAPSHOT.open(newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rn=r["repo_name"].strip()
            if "/" not in rn: continue
            dedup.setdefault(rn.casefold(),rn)
    return sorted(dedup.values(), key=str.casefold)

def inspect_repo(repo_name):
    meta=fetch_json(repo_url(repo_name,"meta.json"))
    row={"repo_name":repo_name,"meta_status":meta["status"],"exported":int(meta["status"]==200)}
    if meta["status"]!=200:
        for m in METRICS:
            row[f"{m}__status"]="SKIP_NOT_EXPORTED"
            row[f"{m}__n24"]=0; row[f"{m}__n36"]=0
            row[f"{m}__raw24"]=0; row[f"{m}__raw36"]=0
        row.update({"first_month":"","last_month":"","full_exposure_24":0,"full_exposure_36":0})
        return row
    all_months=[]
    for m in METRICS:
        x=fetch_json(repo_url(repo_name,m+".json"))
        row[f"{m}__status"]=x["status"]
        p=key_profile(x["json"])
        ms=p["months"]; rs=p["raw_months"]
        all_months.extend(ms)
        row[f"{m}__n24"]=sum(k in W24 for k in ms)
        row[f"{m}__n36"]=sum(k in W36 for k in ms)
        row[f"{m}__raw24"]=sum(k in W24 for k in rs)
        row[f"{m}__raw36"]=sum(k in W36 for k in rs)
    if all_months:
        first=min(all_months); last=max(all_months)
    else:
        first=last=""
    row["first_month"]=first; row["last_month"]=last
    row["full_exposure_24"]=int(bool(first) and first<=W24[0] and last>=W24[-1])
    row["full_exposure_36"]=int(bool(first) and first<=W36[0] and last>=W36[-1])
    return row

def n_ge(rows,col,k):
    return sum(int(r.get(col,0) or 0)>=k for r in rows)

def metric_summary(rows,m):
    vals24=[int(r[f"{m}__n24"]) for r in rows if r["exported"]]
    vals36=[int(r[f"{m}__n36"]) for r in rows if r["exported"]]
    return {
      "file_200":sum(r[f"{m}__status"]==200 for r in rows),
      "file_404":sum(r[f"{m}__status"]==404 for r in rows),
      "file_error":sum(r[f"{m}__status"]=="ERROR" for r in rows),
      "median_explicit_months_24":median(vals24) if vals24 else 0,
      "median_explicit_months_36":median(vals36) if vals36 else 0,
      "repos_ge_6_explicit_months_24":n_ge(rows,f"{m}__n24",6),
      "repos_ge_12_explicit_months_24":n_ge(rows,f"{m}__n24",12),
      "repos_ge_18_explicit_months_24":n_ge(rows,f"{m}__n24",18),
      "repos_all_24_explicit_months":n_ge(rows,f"{m}__n24",24),
      "repos_ge_12_explicit_months_36":n_ge(rows,f"{m}__n36",12),
      "repos_ge_24_explicit_months_36":n_ge(rows,f"{m}__n36",24),
      "repos_all_36_explicit_months":n_ge(rows,f"{m}__n36",36),
      "repos_with_interpolation_raw_flag_24":sum(int(r[f"{m}__raw24"])>0 for r in rows),
      "repos_with_interpolation_raw_flag_36":sum(int(r[f"{m}__raw36"])>0 for r in rows),
      "interpolation_raw_months_24":sum(int(r[f"{m}__raw24"]) for r in rows),
      "interpolation_raw_months_36":sum(int(r[f"{m}__raw36"]) for r in rows),
    }

def main():
    candidates=load_candidates()
    rows=[]
    with ThreadPoolExecutor(max_workers=20) as ex:
        fut={ex.submit(inspect_repo,r):r for r in candidates}
        for i,f in enumerate(as_completed(fut),1):
            rows.append(f.result())
            if i%50==0: print(f"R1C_PROGRESS={i}/{len(candidates)}", flush=True)
    rows.sort(key=lambda r:r["repo_name"].casefold())
    fields=["repo_name","meta_status","exported","first_month","last_month","full_exposure_24","full_exposure_36"]
    for m in METRICS:
        fields += [f"{m}__status",f"{m}__n24",f"{m}__n36",f"{m}__raw24",f"{m}__raw36"]
    OUT_REPO.parent.mkdir(parents=True,exist_ok=True)
    with OUT_REPO.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

    exported=[r for r in rows if r["exported"]]
    full24=[r for r in exported if r["full_exposure_24"]]
    full36=[r for r in exported if r["full_exposure_36"]]
    issue_res_6=sum(int(r["issue_resolution_duration__n24"])>=6 for r in full24)
    issue_res_12=sum(int(r["issue_resolution_duration__n24"])>=12 for r in full24)
    pr_res_6=sum(int(r["change_request_resolution_duration__n24"])>=6 for r in full24)
    pr_res_12=sum(int(r["change_request_resolution_duration__n24"])>=12 for r in full24)
    either_res_6=sum(max(int(r["issue_resolution_duration__n24"]),int(r["change_request_resolution_duration__n24"]))>=6 for r in full24)
    either_res_12=sum(max(int(r["issue_resolution_duration__n24"]),int(r["change_request_resolution_duration__n24"]))>=12 for r in full24)
    both_res_6=sum(int(r["issue_resolution_duration__n24"])>=6 and int(r["change_request_resolution_duration__n24"])>=6 for r in full24)
    both_res_12=sum(int(r["issue_resolution_duration__n24"])>=12 and int(r["change_request_resolution_duration__n24"])>=12 for r in full24)

    summary={
      "protocol":"OMOSSP_R1C_CURATED_PROJECT_FIRST_CANDIDATE_PANEL_COVERAGE_R1",
      "candidate_source":"OSS Compass gitee single-repositories snapshot",
      "candidate_rows_unique_canonical_casefold":len(candidates),
      "candidate_rows_unique_exact_case_in_snapshot":535,
      "casefold_duplicate_note":"motion-code/madong and motion-code/MaDong collapse to one canonical candidate",
      "project_curation_state":"PROVISIONAL_CURATED_SINGLE_REPOSITORY_CANDIDATES__NOT_FINAL_VALIDATED_PROJECT_ENTITIES",
      "opendigger_meta_exported":len(exported),
      "opendigger_meta_not_exported":sum(r["meta_status"]==404 for r in rows),
      "opendigger_meta_errors":sum(r["meta_status"]=="ERROR" for r in rows),
      "window_24":"2024-01..2025-12",
      "window_36":"2023-01..2025-12",
      "N_with_full_observable_envelope_24":len(full24),
      "N_with_full_observable_envelope_36":len(full36),
      "project_month_NT_full_envelope_24":len(full24)*24,
      "project_month_NT_full_envelope_36":len(full36)*36,
      "primary_duration_coverage_among_full24":{
        "issue_resolution_ge6_months":issue_res_6,
        "issue_resolution_ge12_months":issue_res_12,
        "pr_resolution_ge6_months":pr_res_6,
        "pr_resolution_ge12_months":pr_res_12,
        "either_resolution_family_ge6_months":either_res_6,
        "either_resolution_family_ge12_months":either_res_12,
        "both_resolution_families_ge6_months":both_res_6,
        "both_resolution_families_ge12_months":both_res_12
      },
      "metric_coverage":{m:metric_summary(rows,m) for m in METRICS},
      "semantics":{
        "count_metric_absent_month_inside_verified_envelope":"STRUCTURAL_ZERO_ALLOWED",
        "duration_metric_absent_month":"NO_ESTIMABLE_EVENT_POPULATION__NOT_ZERO",
        "raw_suffix_month":"INTERPOLATION_WARNING__PRESERVE_RAW_PROVENANCE"
      },
      "selection_integrity":{
        "metric_values_used_for_candidate_selection":False,
        "metric_values_persisted":False,
        "only_transport_status_and_period_key_presence_persisted":True,
        "performance_ranking_performed":False
      }
    }
    OUT_SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("===== OMOSSP_R1C_SUMMARY_BEGIN =====")
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    print("===== OMOSSP_R1C_SUMMARY_END =====")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
