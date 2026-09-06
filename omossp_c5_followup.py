#!/usr/bin/env python3
from __future__ import annotations
import base64, hashlib, html, json, re, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

UA="OMOSSP-C5-Followup/1.0"
OUT=Path("omossp_c5_followup_output")
OUT.mkdir(exist_ok=True)

def sha(b:bytes)->str: return hashlib.sha256(b).hexdigest()
def nowz()->str: return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def fetch(url:str):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    waits=[2,8,30]
    rec={"url":url,"attempts":[]}
    for attempt in range(1,5):
        t0=time.time()
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                body=r.read()
                rec["attempts"].append({"attempt":attempt,"status":getattr(r,"status",200),"final_url":r.geturl(),"bytes":len(body),"sha256":sha(body),"content_type":r.headers.get("Content-Type"),"elapsed_ms":round((time.time()-t0)*1000)})
                rec["terminal"]="SUCCESS_CAPTURED"; return rec,body
        except urllib.error.HTTPError as e:
            body=e.read() if hasattr(e,"read") else b""
            rec["attempts"].append({"attempt":attempt,"status":e.code,"final_url":getattr(e,"url",url),"bytes":len(body),"sha256":sha(body) if body else None,"elapsed_ms":round((time.time()-t0)*1000)})
            if e.code==404:
                rec["terminal"]="NOT_FOUND_FOR_THIS_ENDPOINT"; return rec,body
            if e.code in (429,500,502,503,504) and attempt<4:
                time.sleep(waits[attempt-1]); continue
            rec["terminal"]="ACCESS_INCOMPLETE_AFTER_RETRIES"; return rec,body
        except Exception as e:
            rec["attempts"].append({"attempt":attempt,"error":type(e).__name__+": "+str(e),"elapsed_ms":round((time.time()-t0)*1000)})
            if attempt<4: time.sleep(waits[attempt-1]); continue
            rec["terminal"]="ACCESS_INCOMPLETE_AFTER_RETRIES"; return rec,b""

def decode(body,ctype):
    if ctype and "application/json" in ctype:
        try: return json.dumps(json.loads(body.decode("utf-8")),ensure_ascii=False,indent=2)
        except Exception: pass
    return body.decode("utf-8",errors="replace").replace("\r\n","\n").replace("\r","\n")

def html_text(s):
    s=re.sub(r"(?is)<script.*?>.*?</script>"," ",s)
    s=re.sub(r"(?is)<style.*?>.*?</style>"," ",s)
    s=re.sub(r"(?s)<[^>]+>","\n",s)
    s=html.unescape(s)
    s=re.sub(r"\n[ \t]+","\n",s)
    s=re.sub(r"\n{3,}","\n\n",s)
    return s.strip()

ROUTES=[
 {"rank":1,"repo":"openharmony/bundlemanager_bundle_framework","class_id":"EC08","evidence_class":"official governance/manifest/release-note evidence","route_basis":"C5_EC08_EXPLICIT_MANIFEST_INCLUDE__ohos/ohos.xml","url":"https://gitee.com/openharmony/manifest/raw/master/ohos/ohos.xml","evidence_type":"OFFICIAL_GOVERNANCE_MANIFEST_INCLUDE"},
 {"rank":10,"repo":"src-openeuler/ghc-regex-posix","class_id":"EC03","evidence_class":"provider-native upstream metadata","route_basis":"C5_EC05_HACKAGE_EXPLICIT_SOURCE_REPO","url":"https://api.github.com/repos/haskell-hvr/regex-posix","evidence_type":"GITHUB_PROVIDER_NATIVE_REPOSITORY_METADATA"},
 {"rank":10,"repo":"src-openeuler/ghc-regex-posix","class_id":"EC06","evidence_class":"official canonical repository README/project docs","route_basis":"C5_EC05_HACKAGE_EXPLICIT_SOURCE_REPO","url":"https://api.github.com/repos/haskell-hvr/regex-posix/readme","evidence_type":"GITHUB_PROVIDER_NATIVE_README"}
]

def card(route,rec,body):
    ctype=rec["attempts"][-1].get("content_type")
    text=decode(body,ctype)
    if route["evidence_type"]=="GITHUB_PROVIDER_NATIVE_README":
        try:
            o=json.loads(body.decode())
            if o.get("encoding")=="base64" and o.get("content"):
                text=base64.b64decode(o["content"]).decode("utf-8",errors="replace")
        except Exception: pass
    if ctype and "text/html" in ctype.lower(): text=html_text(text)
    tb=text.encode("utf-8")
    eid="E_C5F_"+hashlib.sha256(f"{route['rank']}|{route['class_id']}|{route['url']}|{sha(tb)}".encode()).hexdigest()[:24]
    return {
      "evidence_id":eid,"source_scale_rank":route["rank"],"source_repo_name":route["repo"],
      "evidence_grade":"P2","evidence_type":route["evidence_type"],"source_url":route["url"],
      "retrieved_at_utc":nowz(),"capture_method":"GITHUB_ACTIONS_EXACT_HTTPS_GET_R1",
      "raw_sha256_if_available":sha(body),"provider_native_hash_if_available":"",
      "text_extract_sha256":sha(tb),
      "evidence_summary":f"{route['class_id']} exact follow-up capture; route_basis={route['route_basis']}; P1 not assigned during acquisition.",
      "performance_outcomes_accessed":False,"configured_evidence_class":route["evidence_class"],
      "evidence_class_id":route["class_id"],"route_basis":route["route_basis"],"text_extract":text
    }

results=[]
for route in ROUTES:
    rec,body=fetch(route["url"])
    results.append({**route,"transport":rec,"card":card(route,rec,body) if rec["terminal"]=="SUCCESS_CAPTURED" else None})

payload={
 "protocol":"OMOSSP_PHASE_C5_EXPLICIT_LOCATOR_FOLLOWUP_R1",
 "frozen_ranks":[1,10],
 "search_used":False,
 "name_similarity_inference_used":False,
 "performance_outcomes_accessed":False,
 "final_project_entity_id_minted":False,
 "p1_assigned_during_acquisition":False,
 "evidence_exhaustion_claimed":False,
 "results":results
}
canon=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
pretty=json.dumps(payload,ensure_ascii=False,indent=2).encode()
(OUT/"c5_followup.json").write_bytes(pretty)
(OUT/"c5_followup.sha256").write_text(sha(canon)+"  canonical-json\n",encoding="utf-8")
print(json.dumps({"routes":len(results),"cards":sum(1 for x in results if x.get("card")),"canonical_sha256":sha(canon)},indent=2))
