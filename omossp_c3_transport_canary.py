#!/usr/bin/env python3
import hashlib, json, time, urllib.request, urllib.error
from pathlib import Path

UA = "OMOSSP-C3-Transport-Canary/1.0"
OUT = Path("omossp_c3_output")
OUT.mkdir(exist_ok=True)

CASES = [
  {"rank":1,"repo":"openharmony/bundlemanager_bundle_framework","targets":[
    "https://gitee.com/openharmony/bundlemanager_bundle_framework",
    "https://gitee.com/openharmony/bundlemanager_bundle_framework/raw/master/README.md",
    "https://gitee.com/openharmony/bundlemanager_bundle_framework/raw/master/README_zh.md"
  ]},
  {"rank":2,"repo":"src-openeuler/kf5-kplotting","targets":[
    "https://gitee.com/src-openeuler/kf5-kplotting",
    "https://gitee.com/src-openeuler/kf5-kplotting/raw/master/kf5-kplotting.spec",
    "https://gitee.com/src-openeuler/kf5-kplotting/raw/master/kf5-kplotting.spec?inline=false"
  ]},
  {"rank":3,"repo":"src-openeuler/perl-Data-Compare","targets":[
    "https://gitee.com/src-openeuler/perl-Data-Compare",
    "https://gitee.com/src-openeuler/perl-Data-Compare/raw/master/perl-Data-Compare.spec"
  ]},
  {"rank":5,"repo":"src-anolis-os/sos","targets":[
    "https://gitee.com/src-anolis-os/sos",
    "https://gitee.com/src-anolis-os/sos/raw/master/sos.spec"
  ]},
  {"rank":6,"repo":"src-openeuler/python-pyrad","targets":[
    "https://gitee.com/src-openeuler/python-pyrad",
    "https://gitee.com/src-openeuler/python-pyrad/raw/master/python-pyrad.spec"
  ]},
  {"rank":9,"repo":"src-anolis-os/percona-xtrabackup","targets":[
    "https://gitee.com/src-anolis-os/percona-xtrabackup",
    "https://gitee.com/src-anolis-os/percona-xtrabackup/raw/master/percona-xtrabackup.spec"
  ]},
  {"rank":10,"repo":"src-openeuler/ghc-regex-posix","targets":[
    "https://gitee.com/src-openeuler/ghc-regex-posix",
    "https://gitee.com/src-openeuler/ghc-regex-posix/raw/master/ghc-regex-posix.spec"
  ]},
  {"rank":11,"repo":"src-anolis-os/patchelf","targets":[
    "https://gitee.com/src-anolis-os/patchelf",
    "https://gitee.com/src-anolis-os/patchelf/raw/master/patchelf.spec"
  ]}
]

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept":"*/*"})
    rec={"url":url,"attempts":[]}
    for attempt in range(1,5):
        t0=time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body=r.read()
                rec["attempts"].append({
                    "attempt":attempt,"status":getattr(r,"status",200),
                    "final_url":r.geturl(),"bytes":len(body),
                    "sha256":hashlib.sha256(body).hexdigest(),
                    "content_type":r.headers.get("Content-Type"),
                    "elapsed_ms":round((time.time()-t0)*1000)
                })
                rec["terminal"]="SUCCESS_CAPTURED"
                rec["body_sha256"]=hashlib.sha256(body).hexdigest()
                rec["body_bytes"]=len(body)
                return rec, body
        except urllib.error.HTTPError as e:
            b=e.read() if hasattr(e,"read") else b""
            rec["attempts"].append({"attempt":attempt,"status":e.code,"final_url":getattr(e,"url",url),
                                    "bytes":len(b),"sha256":hashlib.sha256(b).hexdigest() if b else None,
                                    "elapsed_ms":round((time.time()-t0)*1000)})
            if e.code==404:
                rec["terminal"]="NOT_FOUND_FOR_THIS_ENDPOINT"
                return rec,b
            if e.code in (429,500,502,503,504):
                if attempt<4: time.sleep([2,8,30][attempt-1]); continue
                rec["terminal"]="ACCESS_INCOMPLETE_AFTER_RETRIES"; return rec,b
            rec["terminal"]="ACCESS_INCOMPLETE_AFTER_RETRIES"; return rec,b
        except Exception as e:
            rec["attempts"].append({"attempt":attempt,"error":type(e).__name__+": "+str(e),
                                    "elapsed_ms":round((time.time()-t0)*1000)})
            if attempt<4: time.sleep([2,8,30][attempt-1]); continue
            rec["terminal"]="ACCESS_INCOMPLETE_AFTER_RETRIES"; return rec,b""

all_results=[]
for case in CASES:
    cr={"rank":case["rank"],"repo":case["repo"],"performance_outcomes_accessed":False,"targets":[]}
    for idx,url in enumerate(case["targets"],1):
        rec,body=fetch(url)
        rec["target_index"]=idx
        cr["targets"].append(rec)
        if body:
            fn=OUT/f"rank_{case['rank']:05d}_target_{idx:02d}.bin"
            fn.write_bytes(body)
    all_results.append(cr)

payload={
  "protocol":"OMOSSP_PHASE_C3_EXACT_EVIDENCE_TRANSPORT_CANARY_R1",
  "frozen_ranks":[1,2,3,5,6,9,10,11],
  "search_used":False,
  "name_similarity_inference_used":False,
  "performance_outcomes_accessed":False,
  "final_project_entity_id_minted":False,
  "results":all_results
}
data=json.dumps(payload,ensure_ascii=False,indent=2).encode()
(OUT/"transport_result.json").write_bytes(data)
(OUT/"transport_result.sha256").write_text(hashlib.sha256(data).hexdigest()+"  transport_result.json\n")
print(json.dumps({"rows":len(all_results),"sha256":hashlib.sha256(data).hexdigest()},indent=2))
