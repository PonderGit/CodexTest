#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, re, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

UA="OMOSSP-C4-Materializer/1.0"
OUT=Path("omossp_c4_output")
OUT.mkdir(exist_ok=True)

# Frozen cohort: unchanged from C2/C3.
CASES=[
 {"rank":1,"repo":"openharmony/bundlemanager_bundle_framework","container":"UNKNOWN","targets":[
   {"class_id":"EC01","evidence_class":"exact source repository README/project docs","url":"https://gitee.com/openharmony/bundlemanager_bundle_framework/raw/master/README_zh.md","evidence_type":"EXACT_SOURCE_REPOSITORY_README"}
 ]},
 {"rank":2,"repo":"src-openeuler/kf5-kplotting","container":"PACKAGE_CONTAINER","targets":[
   {"class_id":"EC01","evidence_class":"exact source repository README/project docs","url":"https://gitee.com/src-openeuler/kf5-kplotting","evidence_type":"EXACT_SOURCE_REPOSITORY_PAGE"},
   {"class_id":"EC02","evidence_class":"exact package spec/source/homepage/VCS metadata","url":"https://gitee.com/src-openeuler/kf5-kplotting/raw/master/kf5-kplotting.spec","evidence_type":"EXACT_PACKAGE_SPEC_METADATA"}
 ]},
 {"rank":3,"repo":"src-openeuler/perl-Data-Compare","container":"PACKAGE_CONTAINER","targets":[
   {"class_id":"EC01","evidence_class":"exact source repository README/project docs","url":"https://gitee.com/src-openeuler/perl-Data-Compare","evidence_type":"EXACT_SOURCE_REPOSITORY_PAGE"},
   {"class_id":"EC02","evidence_class":"exact package spec/source/homepage/VCS metadata","url":"https://gitee.com/src-openeuler/perl-Data-Compare/raw/master/perl-Data-Compare.spec","evidence_type":"EXACT_PACKAGE_SPEC_METADATA"}
 ]},
 {"rank":5,"repo":"src-anolis-os/sos","container":"PACKAGE_CONTAINER","targets":[
   {"class_id":"EC01","evidence_class":"exact source repository README/project docs","url":"https://gitee.com/src-anolis-os/sos","evidence_type":"EXACT_SOURCE_REPOSITORY_PAGE"},
   {"class_id":"EC02","evidence_class":"exact package spec/source/homepage/VCS metadata","url":"https://gitee.com/src-anolis-os/sos/raw/master/sos.spec","evidence_type":"EXACT_PACKAGE_SPEC_METADATA"}
 ]},
 {"rank":6,"repo":"src-openeuler/python-pyrad","container":"PACKAGE_CONTAINER","targets":[
   {"class_id":"EC01","evidence_class":"exact source repository README/project docs","url":"https://gitee.com/src-openeuler/python-pyrad","evidence_type":"EXACT_SOURCE_REPOSITORY_PAGE"},
   {"class_id":"EC02","evidence_class":"exact package spec/source/homepage/VCS metadata","url":"https://gitee.com/src-openeuler/python-pyrad/raw/master/python-pyrad.spec","evidence_type":"EXACT_PACKAGE_SPEC_METADATA"}
 ]},
 {"rank":9,"repo":"src-anolis-os/percona-xtrabackup","container":"PACKAGE_CONTAINER","targets":[
   {"class_id":"EC01","evidence_class":"exact source repository README/project docs","url":"https://gitee.com/src-anolis-os/percona-xtrabackup","evidence_type":"EXACT_SOURCE_REPOSITORY_PAGE"},
   {"class_id":"EC02","evidence_class":"exact package spec/source/homepage/VCS metadata","url":"https://gitee.com/src-anolis-os/percona-xtrabackup/raw/master/percona-xtrabackup.spec","evidence_type":"EXACT_PACKAGE_SPEC_METADATA"}
 ]},
 {"rank":10,"repo":"src-openeuler/ghc-regex-posix","container":"PACKAGE_CONTAINER","targets":[
   {"class_id":"EC01","evidence_class":"exact source repository README/project docs","url":"https://gitee.com/src-openeuler/ghc-regex-posix","evidence_type":"EXACT_SOURCE_REPOSITORY_PAGE"},
   {"class_id":"EC02","evidence_class":"exact package spec/source/homepage/VCS metadata","url":"https://gitee.com/src-openeuler/ghc-regex-posix/raw/master/ghc-regex-posix.spec","evidence_type":"EXACT_PACKAGE_SPEC_METADATA"}
 ]},
 {"rank":11,"repo":"src-anolis-os/patchelf","container":"PACKAGE_CONTAINER","targets":[
   {"class_id":"EC01","evidence_class":"exact source repository README/project docs","url":"https://gitee.com/src-anolis-os/patchelf","evidence_type":"EXACT_SOURCE_REPOSITORY_PAGE"},
   {"class_id":"EC02","evidence_class":"exact package spec/source/homepage/VCS metadata","url":"https://gitee.com/src-anolis-os/patchelf/raw/master/patchelf.spec","evidence_type":"EXACT_PACKAGE_SPEC_METADATA"}
 ]}
]

def sha(b:bytes)->str:
    return hashlib.sha256(b).hexdigest()

def nowz()->str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def normalize_text(body:bytes)->str:
    txt=body.decode("utf-8",errors="replace").replace("\r\n","\n").replace("\r","\n")
    return txt

LOCATOR_LINE=re.compile(r"^(URL|Homepage|HomePage|Source\d*|VCS|SCM|Upstream|ProjectURL)\s*:\s*(.+)$",re.I)
URL_RE=re.compile(r"https?://[^\s<>'\"\)\]]+")

def explicit_locators(text:str):
    out=[]
    for line in text.splitlines():
        m=LOCATOR_LINE.match(line.strip())
        if not m: continue
        field=m.group(1)
        value=m.group(2).strip()
        urls=URL_RE.findall(value)
        out.append({"field":field,"value":value,"urls":urls})
    return out

def fetch(url:str):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    rec={"url":url,"attempts":[]}
    waits=[2,8,30]
    for attempt in range(1,5):
        t0=time.time()
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                body=r.read()
                rec["attempts"].append({"attempt":attempt,"status":getattr(r,"status",200),"final_url":r.geturl(),"bytes":len(body),"sha256":sha(body),"content_type":r.headers.get("Content-Type"),"elapsed_ms":round((time.time()-t0)*1000)})
                rec["terminal"]="SUCCESS_CAPTURED"
                return rec,body
        except urllib.error.HTTPError as e:
            body=e.read() if hasattr(e,"read") else b""
            rec["attempts"].append({"attempt":attempt,"status":e.code,"final_url":getattr(e,"url",url),"bytes":len(body),"sha256":sha(body) if body else None,"elapsed_ms":round((time.time()-t0)*1000)})
            if e.code==404:
                rec["terminal"]="NOT_FOUND_FOR_THIS_ENDPOINT"; return rec,body
            if e.code in (429,500,502,503,504):
                if attempt<4: time.sleep(waits[attempt-1]); continue
            rec["terminal"]="ACCESS_INCOMPLETE_AFTER_RETRIES"; return rec,body
        except Exception as e:
            rec["attempts"].append({"attempt":attempt,"error":type(e).__name__+": "+str(e),"elapsed_ms":round((time.time()-t0)*1000)})
            if attempt<4: time.sleep(waits[attempt-1]); continue
            rec["terminal"]="ACCESS_INCOMPLETE_AFTER_RETRIES"; return rec,b""

def evidence_card(case,target,rec,body):
    text=normalize_text(body)
    text_b=text.encode("utf-8")
    text_sha=sha(text_b)
    eid="E_C4_"+hashlib.sha256(f"{case['rank']}|{case['repo']}|{target['class_id']}|{target['url']}|{text_sha}".encode()).hexdigest()[:24]
    loc=explicit_locators(text)
    summary=f"{target['class_id']} exact public capture; text bytes={len(text_b)}; explicit locator fields={len(loc)}. Locator fields remain locator-only and are not P1 by themselves."
    return {
      "evidence_id":eid,
      "source_scale_rank":case["rank"],
      "source_repo_name":case["repo"],
      "source_container_class":case["container"],
      "configured_evidence_class":target["evidence_class"],
      "evidence_class_id":target["class_id"],
      "evidence_grade":"P2",
      "evidence_type":target["evidence_type"],
      "source_url":target["url"],
      "final_url":rec["attempts"][-1].get("final_url",target["url"]),
      "retrieved_at_utc":nowz(),
      "capture_method":"GITHUB_ACTIONS_EXACT_HTTPS_GET_R1",
      "raw_sha256_if_available":sha(body),
      "provider_native_hash_if_available":"",
      "text_extract_sha256":text_sha,
      "evidence_summary":summary,
      "performance_outcomes_accessed":False,
      "text_extract":text,
      "explicit_locator_fields":loc,
      "p1_interpretation":"NOT_ASSIGNED__SOURCE_CONTROLLED_LOCATOR_OR_SOURCE_DOC_ONLY"
    }

results=[]
for case in CASES:
    cr={"rank":case["rank"],"repo":case["repo"],"source_container_class":case["container"],"attempts":[],"cards":[]}
    for target in case["targets"]:
        rec,body=fetch(target["url"])
        rec.update({"evidence_class_id":target["class_id"],"configured_evidence_class":target["evidence_class"],"evidence_type":target["evidence_type"]})
        cr["attempts"].append(rec)
        if rec["terminal"]=="SUCCESS_CAPTURED":
            cr["cards"].append(evidence_card(case,target,rec,body))
    # Important: do not claim evidence exhaustion; only EC01/EC02 are exercised here.
    cr["evidence_exhaustion_eligible"]=False
    cr["decision_template_proposed"]=None
    cr["proposed_identity"]={}
    results.append(cr)

payload={
 "protocol":"OMOSSP_PHASE_C4_CONTRACT_ALIGNED_MATERIALIZATION_R1",
 "frozen_ranks":[1,2,3,5,6,9,10,11],
 "configured_evidence_classes_exercised":["EC01","EC02"],
 "all_eight_classes_exhausted":False,
 "search_used":False,
 "name_similarity_inference_used":False,
 "performance_outcomes_accessed":False,
 "final_project_entity_id_minted":False,
 "cards_are_p1":False,
 "results":results
}
raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
pretty=json.dumps(payload,ensure_ascii=False,indent=2).encode("utf-8")
(OUT/"c4_materialized.json").write_bytes(pretty)
(OUT/"c4_canonical.sha256").write_text(sha(raw)+"  canonical-json\n",encoding="utf-8")
print(json.dumps({"rows":len(results),"cards":sum(len(r["cards"]) for r in results),"canonical_sha256":sha(raw)},indent=2))
