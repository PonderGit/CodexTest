#!/usr/bin/env python3
import csv, json, os, re, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

IN_COVERAGE=Path("governance/r1d_github_project_first_panel_coverage_by_repo.csv")
OUT_REPO=Path("governance/r3_outcome_blind_project_curation_variable_coverage_by_repo.csv")
OUT_SUMMARY=Path("governance/r3_outcome_blind_project_curation_variable_coverage_summary.json")

GITHUB_API="https://api.github.com/repos"
OD_BASE="https://oss.open-digger.cn/github"
UA="OMOSSP-R3-outcome-blind-curation/1.0"
TOKEN=os.environ.get("GITHUB_TOKEN","")

W24=[f"{y:04d}-{m:02d}" for y,m in [(2024,m) for m in range(1,13)]+[(2025,m) for m in range(1,13)]]
MONTH_RE=re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")

HARD_META_REPOS={".github"}
NONSOFTWARE_TERMS=[
  "documentation","docs-only","docs only","dataset","datasets","tutorial","tutorials",
  "course","courses","workshop","workshops","slides","awesome-list","awesome list",
  "example-only","example only","demo-only","demo only","benchmark-only","benchmark only",
  "paper-code-free","data-only","data only"
]
NAME_SIGNAL_RE=re.compile(r"(^|[-_.])(docs?|documentation|datasets?|tutorials?|courses?|slides|awesome|examples?|demos?|benchmarks?)([-_.]|$)",re.I)

def http_json(url, headers=None, attempts=3, timeout=25):
    h={"User-Agent":UA,"Accept":"application/vnd.github+json"}
    if headers: h.update(headers)
    last=None
    for i in range(attempts):
        try:
            req=urllib.request.Request(url,headers=h)
            with urllib.request.urlopen(req,timeout=timeout) as r:
                raw=r.read()
                return int(r.status),json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (404,451): return e.code,None
            last=f"HTTP_{e.code}"
            if e.code not in (403,429,500,502,503,504): break
        except Exception as e:
            last=type(e).__name__
        time.sleep(0.4*(2**i))
    return "ERROR",{"error":last}

def github_meta(repo):
    headers={}
    if TOKEN: headers["Authorization"]=f"Bearer {TOKEN}"
    return http_json(f"{GITHUB_API}/{quote(repo,safe='/')}",headers=headers)

def od_json(repo,metric):
    owner,name=repo.split("/",1)
    return http_json(f"{OD_BASE}/{quote(owner,safe='')}/{quote(name,safe='')}/{metric}.json",
                     headers={"Accept":"application/json"})

def load_full24():
    out=[]
    seen=set()
    with IN_COVERAGE.open(newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("full_exposure_24")!="1": continue
            rn=r["repo_name"].strip()
            k=rn.casefold()
            if k in seen: continue
            seen.add(k); out.append(rn)
    return sorted(out,key=str.casefold)

def recurse_months_for_field(obj, field):
    if not isinstance(obj,dict) or field not in obj: return set()
    node=obj[field]
    if not isinstance(node,dict): return set()
    return {str(k) for k in node.keys() if MONTH_RE.match(str(k)) and str(k) in W24}

def top_months(obj):
    if not isinstance(obj,dict): return set()
    return {str(k) for k in obj.keys() if MONTH_RE.match(str(k)) and str(k) in W24}

def source_structure(obj,metric):
    # Exact field coverage only; numerical magnitudes are neither retained nor evaluated.
    if metric in ("issue_resolution_duration","issue_age"):
        return {
          "q2_months":recurse_months_for_field(obj,"quantile_2"),
          "levels_months":recurse_months_for_field(obj,"levels"),
          "has_q2":int(isinstance(obj,dict) and isinstance(obj.get("quantile_2"),dict)),
          "has_levels":int(isinstance(obj,dict) and isinstance(obj.get("levels"),dict))
        }
    return {"months":top_months(obj)}

def manual_signal(meta, requested):
    reasons=[]
    if not isinstance(meta,dict): return ["META_UNAVAILABLE"]
    name=str(meta.get("name") or "")
    desc=str(meta.get("description") or "")
    topics=meta.get("topics") or []
    lang=meta.get("language")
    full=str(meta.get("full_name") or "")
    if meta.get("archived"): reasons.append("ARCHIVED_CURRENT_STATE")
    if meta.get("disabled"): reasons.append("DISABLED_CURRENT_STATE")
    if not lang: reasons.append("NO_DOMINANT_LANGUAGE")
    if full and full.casefold()!=requested.casefold(): reasons.append("CANONICAL_REDIRECT_OR_TRANSFER")
    hay=" ".join([name,desc]+[str(x) for x in topics]).lower()
    if NAME_SIGNAL_RE.search(name): reasons.append("NONSOFTWARE_NAME_SIGNAL")
    if any(t in hay for t in NONSOFTWARE_TERMS): reasons.append("NONSOFTWARE_TEXT_SIGNAL")
    if "mirror" in name.lower() or "mirror" in topics: reasons.append("MIRROR_TEXT_SIGNAL")
    return sorted(set(reasons))

def inspect(repo):
    gs,meta=github_meta(repo)
    row={"repo_name":repo,"github_status":gs}
    if gs!=200 or not isinstance(meta,dict):
        row.update({"curation_state":"MANUAL_REVIEW","curation_reason":"META_UNAVAILABLE",
                    "canonical_full_name":"","language":"","fork":"","mirror_url":"","is_template":"",
                    "archived":"","disabled":""})
    else:
        name=str(meta.get("name") or "")
        hard=[]
        if bool(meta.get("fork")): hard.append("GITHUB_FORK")
        if meta.get("mirror_url"): hard.append("GITHUB_MIRROR_URL")
        if bool(meta.get("is_template")): hard.append("GITHUB_TEMPLATE")
        if name in HARD_META_REPOS: hard.append("ORG_META_REPOSITORY")
        manual=manual_signal(meta,repo)
        if hard:
            state="AUTO_EXCLUDE"; reason=";".join(sorted(set(hard)))
        elif manual:
            state="MANUAL_REVIEW"; reason=";".join(manual)
        else:
            state="AUTO_INCLUDE"; reason="PASS_PROSPECTIVE_METADATA_RULES"
        row.update({
          "curation_state":state,"curation_reason":reason,
          "canonical_full_name":str(meta.get("full_name") or ""),
          "language":str(meta.get("language") or ""),
          "fork":int(bool(meta.get("fork"))),
          "mirror_url":str(meta.get("mirror_url") or ""),
          "is_template":int(bool(meta.get("is_template"))),
          "archived":int(bool(meta.get("archived"))),
          "disabled":int(bool(meta.get("disabled")))
        })

    metrics={}
    for metric in ["issue_resolution_duration","issue_age","issues_new","contributors","code_change_lines_sum"]:
        st,obj=od_json(repo,metric)
        metrics[metric]={"status":st}
        if st==200 and isinstance(obj,dict):
            metrics[metric].update(source_structure(obj,metric))
        else:
            metrics[metric].update({})

    res=metrics["issue_resolution_duration"]
    age=metrics["issue_age"]
    count_ok=all(metrics[m]["status"]==200 for m in ["issues_new","contributors","code_change_lines_sum"])
    res_m=set(res.get("q2_months",set()))
    age_m=set(age.get("q2_months",set()))
    age_levels=set(age.get("levels_months",set()))

    modelA=sorted(res_m & age_m) if count_ok else []
    # Model B backlog burden can use explicit levels months; zero semantics beyond explicit levels
    # are NOT extended here; this is a conservative exact-field coverage count.
    modelB=sorted(res_m & age_levels) if count_ok else []
    modelC=sorted(res_m) if count_ok else []
    modelD=sorted(age_m) if count_ok else []

    row.update({
      "issue_resolution_status":res["status"],
      "issue_resolution_has_q2":res.get("has_q2",0),
      "issue_resolution_q2_n24":len(res_m),
      "issue_age_status":age["status"],
      "issue_age_has_q2":age.get("has_q2",0),
      "issue_age_q2_n24":len(age_m),
      "issue_age_has_levels":age.get("has_levels",0),
      "issue_age_levels_n24":len(age_levels),
      "issues_new_status":metrics["issues_new"]["status"],
      "contributors_status":metrics["contributors"]["status"],
      "code_change_lines_sum_status":metrics["code_change_lines_sum"]["status"],
      "modelA_usable_months":len(modelA),
      "modelB_usable_months_conservative":len(modelB),
      "modelC_usable_months":len(modelC),
      "modelD_usable_months":len(modelD)
    })
    return row

def n_projects(rows,state,field,k):
    return sum(r["curation_state"]==state and int(r[field])>=k for r in rows)

def nt(rows,state,field):
    return sum(int(r[field]) for r in rows if r["curation_state"]==state)

def main():
    repos=load_full24()
    rows=[]
    with ThreadPoolExecutor(max_workers=24) as ex:
        fut={ex.submit(inspect,r):r for r in repos}
        for i,f in enumerate(as_completed(fut),1):
            try: rows.append(f.result())
            except Exception as e:
                rows.append({"repo_name":fut[f],"github_status":"ERROR","curation_state":"MANUAL_REVIEW",
                             "curation_reason":"UNHANDLED_"+type(e).__name__,
                             "canonical_full_name":"","language":"","fork":"","mirror_url":"","is_template":"",
                             "archived":"","disabled":"","issue_resolution_status":"ERROR","issue_resolution_has_q2":0,
                             "issue_resolution_q2_n24":0,"issue_age_status":"ERROR","issue_age_has_q2":0,
                             "issue_age_q2_n24":0,"issue_age_has_levels":0,"issue_age_levels_n24":0,
                             "issues_new_status":"ERROR","contributors_status":"ERROR","code_change_lines_sum_status":"ERROR",
                             "modelA_usable_months":0,"modelB_usable_months_conservative":0,
                             "modelC_usable_months":0,"modelD_usable_months":0})
            if i%100==0: print(f"R3_PROGRESS={i}/{len(repos)}",flush=True)
    rows.sort(key=lambda x:x["repo_name"].casefold())

    fields=[
      "repo_name","github_status","curation_state","curation_reason","canonical_full_name","language",
      "fork","mirror_url","is_template","archived","disabled",
      "issue_resolution_status","issue_resolution_has_q2","issue_resolution_q2_n24",
      "issue_age_status","issue_age_has_q2","issue_age_q2_n24","issue_age_has_levels","issue_age_levels_n24",
      "issues_new_status","contributors_status","code_change_lines_sum_status",
      "modelA_usable_months","modelB_usable_months_conservative","modelC_usable_months","modelD_usable_months"
    ]
    OUT_REPO.parent.mkdir(parents=True,exist_ok=True)
    with OUT_REPO.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)

    states={s:sum(r["curation_state"]==s for r in rows) for s in ["AUTO_INCLUDE","MANUAL_REVIEW","AUTO_EXCLUDE"]}
    reasons={}
    for r in rows:
        for reason in str(r["curation_reason"]).split(";"):
            if reason: reasons[reason]=reasons.get(reason,0)+1

    coverage={}
    for model,field in [
      ("A","modelA_usable_months"),
      ("B_conservative","modelB_usable_months_conservative"),
      ("C","modelC_usable_months"),
      ("D","modelD_usable_months")
    ]:
        coverage[model]={
          "AUTO_INCLUDE_projects_ge2_months":n_projects(rows,"AUTO_INCLUDE",field,2),
          "AUTO_INCLUDE_projects_ge6_months":n_projects(rows,"AUTO_INCLUDE",field,6),
          "AUTO_INCLUDE_projects_ge12_months":n_projects(rows,"AUTO_INCLUDE",field,12),
          "AUTO_INCLUDE_projects_ge18_months":n_projects(rows,"AUTO_INCLUDE",field,18),
          "AUTO_INCLUDE_project_month_NT":nt(rows,"AUTO_INCLUDE",field),
          "AUTO_INCLUDE_plus_MANUAL_projects_ge2_months":
             sum(r["curation_state"]!="AUTO_EXCLUDE" and int(r[field])>=2 for r in rows),
          "AUTO_INCLUDE_plus_MANUAL_projects_ge12_months":
             sum(r["curation_state"]!="AUTO_EXCLUDE" and int(r[field])>=12 for r in rows)
        }

    summary={
      "protocol":"OMOSSP_R3_OUTCOME_BLIND_PROJECT_CURATION_EXACT_VARIABLE_COVERAGE_R1",
      "input_full24_candidates":len(repos),
      "curation_states":states,
      "curation_reason_counts":dict(sorted(reasons.items())),
      "hard_auto_exclusions":[
        "GitHub fork flag",
        "GitHub mirror_url",
        "GitHub template flag",
        "repository name exactly .github"
      ],
      "manual_review_signals":[
        "current archived/disabled state",
        "no dominant language",
        "canonical redirect/transfer",
        "strong docs/data/tutorial/course/demo/example/benchmark naming or text signals",
        "mirror text signal"
      ],
      "performance_values_used_for_curation":False,
      "metric_magnitudes_persisted":False,
      "coverage_only_transport_note":"OpenDigger JSON is transported only to inspect field/month-key structure; numerical magnitudes are not persisted, ranked, or used for curation.",
      "frozen_variable_file_status":{
        "issue_resolution_200":sum(r["issue_resolution_status"]==200 for r in rows),
        "issue_age_200":sum(r["issue_age_status"]==200 for r in rows),
        "issues_new_200":sum(r["issues_new_status"]==200 for r in rows),
        "contributors_200":sum(r["contributors_status"]==200 for r in rows),
        "code_change_lines_sum_200":sum(r["code_change_lines_sum_status"]==200 for r in rows),
        "all_context_files_200":sum(r["issues_new_status"]==200 and r["contributors_status"]==200 and r["code_change_lines_sum_status"]==200 for r in rows)
      },
      "model_coverage":coverage,
      "sample_floor_projects":500,
      "preferred_projects":750,
      "decision_rule":{
        "quantity_pass":"AUTO_INCLUDE projects with >=2 usable months in primary Model A >=500",
        "robustness_health_check":"Report AUTO_INCLUDE projects with >=12 usable months; do not use this threshold to select the primary sample unless separately justified.",
        "supplement_reopen":"Only if primary Model A AUTO_INCLUDE N<500 or later construct-critical coverage falls below 500."
      },
      "modelB_note":"Model B count coverage is deliberately conservative: only months with explicit issue_age levels are counted. Potential zero-backlog structural months are not imputed in R3.",
      "selection_integrity":{
        "performance_ranking":False,
        "outcome_magnitude_inspected_by_script":False,
        "sample_selection_uses_only_metadata_and_field_presence":True
      }
    }
    OUT_SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("===== OMOSSP_R3_SUMMARY_BEGIN =====")
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    print("===== OMOSSP_R3_SUMMARY_END =====")

if __name__=="__main__":
    main()
