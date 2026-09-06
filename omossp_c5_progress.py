#!/usr/bin/env python3
from __future__ import annotations
import base64, hashlib, html, json, re, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

UA="OMOSSP-C5-Evidence-Progression/1.0"
OUT=Path("omossp_c5_output")
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
                rec["attempts"].append({
                    "attempt":attempt,"status":getattr(r,"status",200),"final_url":r.geturl(),
                    "bytes":len(body),"sha256":sha(body),"content_type":r.headers.get("Content-Type"),
                    "elapsed_ms":round((time.time()-t0)*1000)
                })
                rec["terminal"]="SUCCESS_CAPTURED"
                return rec,body
        except urllib.error.HTTPError as e:
            body=e.read() if hasattr(e,"read") else b""
            rec["attempts"].append({
                "attempt":attempt,"status":e.code,"final_url":getattr(e,"url",url),
                "bytes":len(body),"sha256":sha(body) if body else None,
                "elapsed_ms":round((time.time()-t0)*1000)
            })
            if e.code==404:
                rec["terminal"]="NOT_FOUND_FOR_THIS_ENDPOINT"; return rec,body
            if e.code in (429,500,502,503,504) and attempt<4:
                time.sleep(waits[attempt-1]); continue
            rec["terminal"]="ACCESS_INCOMPLETE_AFTER_RETRIES"; return rec,body
        except Exception as e:
            rec["attempts"].append({"attempt":attempt,"error":type(e).__name__+": "+str(e),"elapsed_ms":round((time.time()-t0)*1000)})
            if attempt<4: time.sleep(waits[attempt-1]); continue
            rec["terminal"]="ACCESS_INCOMPLETE_AFTER_RETRIES"; return rec,b""

URL_RE=re.compile(r"https?://[^\s<>'\"\)\]]+")
LOCATOR_LINE=re.compile(r"^(URL|Homepage|HomePage|Source\d*|VCS|SCM|Upstream|ProjectURL)\s*:\s*(.+)$",re.I)

def decode_text(body:bytes,ctype:str|None)->str:
    if ctype and "application/json" in ctype:
        try: return json.dumps(json.loads(body.decode("utf-8")),ensure_ascii=False,indent=2)
        except Exception: pass
    return body.decode("utf-8",errors="replace").replace("\r\n","\n").replace("\r","\n")

def html_to_text(s:str)->str:
    s=re.sub(r"(?is)<script.*?>.*?</script>"," ",s)
    s=re.sub(r"(?is)<style.*?>.*?</style>"," ",s)
    s=re.sub(r"(?s)<[^>]+>","\n",s)
    s=html.unescape(s)
    s=re.sub(r"\n[ \t]+","\n",s)
    s=re.sub(r"\n{3,}","\n\n",s)
    return s.strip()

def explicit_urls(text:str):
    return sorted(set(URL_RE.findall(text)))

def locator_fields(text:str):
    out=[]
    for line in text.splitlines():
        m=LOCATOR_LINE.match(line.strip())
        if m:
            out.append({"field":m.group(1),"value":m.group(2).strip(),"urls":URL_RE.findall(m.group(2))})
    return out

# All C5 routes are frozen from C4 source-controlled evidence or exact provider/governance routes.
# No name-similarity search is used.
ROUTES=[
 {"rank":1,"repo":"openharmony/bundlemanager_bundle_framework","class_id":"EC08","evidence_class":"official governance/manifest/release-note evidence","route_basis":"EXACT_OPENHARMONY_OFFICIAL_MANIFEST_ROUTE","url":"https://gitee.com/openharmony/manifest/raw/master/default.xml","evidence_type":"OFFICIAL_GOVERNANCE_MANIFEST"},
 {"rank":2,"repo":"src-openeuler/kf5-kplotting","class_id":"EC06","evidence_class":"official canonical repository README/project docs","route_basis":"C4_EC02_URL_MACRO_EXPANSION__framework=kplotting","url":"https://invent.kde.org/frameworks/kplotting","evidence_type":"EXPLICIT_LOCATOR_CANONICAL_REPOSITORY_CANDIDATE"},
 {"rank":2,"repo":"src-openeuler/kf5-kplotting","class_id":"EC07","evidence_class":"official migration/mirror/deprecation notice","route_basis":"C4_EC01_EXPLICIT_MIGRATION_LINK","url":"https://atomgit.com/src-openeuler/kf5-kplotting","evidence_type":"SOURCE_CONTAINER_MIGRATION_NOTICE"},
 {"rank":3,"repo":"src-openeuler/perl-Data-Compare","class_id":"EC05","evidence_class":"official project/distribution registry","route_basis":"C4_EC02_EXACT_URL_FIELD","url":"https://metacpan.org/release/Data-Compare","evidence_type":"EXPLICIT_LOCATOR_OFFICIAL_REGISTRY_CANDIDATE"},
 {"rank":3,"repo":"src-openeuler/perl-Data-Compare","class_id":"EC07","evidence_class":"official migration/mirror/deprecation notice","route_basis":"C4_EC01_EXPLICIT_MIGRATION_LINK","url":"https://atomgit.com/src-openeuler/perl-Data-Compare","evidence_type":"SOURCE_CONTAINER_MIGRATION_NOTICE"},
 {"rank":5,"repo":"src-anolis-os/sos","class_id":"EC02","evidence_class":"exact package spec/source/homepage/VCS metadata","route_basis":"C4_EC01_DEFAULT_BRANCH_a8_PLUS_EXACT_SPEC_NAME","url":"https://gitee.com/src-anolis-os/sos/raw/a8/sos.spec","evidence_type":"EXACT_PACKAGE_SPEC_METADATA_BRANCH_RETRY"},
 {"rank":6,"repo":"src-openeuler/python-pyrad","class_id":"EC03","evidence_class":"provider-native upstream metadata","route_basis":"C4_EC02_EXACT_URL_FIELD","url":"https://api.github.com/repos/pyradius/pyrad","evidence_type":"GITHUB_PROVIDER_NATIVE_REPOSITORY_METADATA"},
 {"rank":6,"repo":"src-openeuler/python-pyrad","class_id":"EC06","evidence_class":"official canonical repository README/project docs","route_basis":"C4_EC02_EXACT_URL_FIELD","url":"https://api.github.com/repos/pyradius/pyrad/readme","evidence_type":"GITHUB_PROVIDER_NATIVE_README"},
 {"rank":6,"repo":"src-openeuler/python-pyrad","class_id":"EC07","evidence_class":"official migration/mirror/deprecation notice","route_basis":"C4_EC01_EXPLICIT_MIGRATION_LINK","url":"https://atomgit.com/src-openeuler/python-pyrad","evidence_type":"SOURCE_CONTAINER_MIGRATION_NOTICE"},
 {"rank":9,"repo":"src-anolis-os/percona-xtrabackup","class_id":"EC01","evidence_class":"exact source repository README/project docs","route_basis":"C4_EC01_DEFAULT_BRANCH_master_EXACT_TREE","url":"https://gitee.com/src-anolis-os/percona-xtrabackup/tree/master","evidence_type":"EXACT_SOURCE_REPOSITORY_TREE"},
 {"rank":10,"repo":"src-openeuler/ghc-regex-posix","class_id":"EC05","evidence_class":"official project/distribution registry","route_basis":"C4_EC02_URL_MACRO_EXPANSION__pkg_name=regex-posix","url":"https://hackage.haskell.org/package/regex-posix","evidence_type":"EXPLICIT_LOCATOR_OFFICIAL_REGISTRY_CANDIDATE"},
 {"rank":10,"repo":"src-openeuler/ghc-regex-posix","class_id":"EC07","evidence_class":"official migration/mirror/deprecation notice","route_basis":"C4_EC01_EXPLICIT_MIGRATION_LINK","url":"https://atomgit.com/src-openeuler/ghc-regex-posix","evidence_type":"SOURCE_CONTAINER_MIGRATION_NOTICE"},
 {"rank":11,"repo":"src-anolis-os/patchelf","class_id":"EC01","evidence_class":"exact source repository README/project docs","route_basis":"C4_EC01_DEFAULT_BRANCH_master_EXACT_TREE","url":"https://gitee.com/src-anolis-os/patchelf/tree/master","evidence_type":"EXACT_SOURCE_REPOSITORY_TREE"}
]

def make_card(route,rec,body):
    ctype=rec["attempts"][-1].get("content_type")
    text=decode_text(body,ctype)
    # For GitHub README API, decode content deterministically when available.
    decoded_readme=None
    if route["evidence_type"]=="GITHUB_PROVIDER_NATIVE_README":
        try:
            obj=json.loads(body.decode("utf-8"))
            if obj.get("encoding")=="base64" and obj.get("content"):
                decoded_readme=base64.b64decode(obj["content"]).decode("utf-8",errors="replace")
                text=decoded_readme
        except Exception:
            pass
    # HTML pages get a bounded readable extract while raw SHA remains over exact bytes.
    if ctype and "text/html" in ctype.lower():
        readable=html_to_text(text)
    else:
        readable=text
    text_bytes=readable.encode("utf-8")
    eid="E_C5_"+hashlib.sha256(f"{route['rank']}|{route['class_id']}|{route['url']}|{sha(text_bytes)}".encode()).hexdigest()[:24]
    return {
      "evidence_id":eid,
      "source_scale_rank":route["rank"],
      "source_repo_name":route["repo"],
      "evidence_grade":"P2",
      "evidence_type":route["evidence_type"],
      "source_url":route["url"],
      "retrieved_at_utc":nowz(),
      "capture_method":"GITHUB_ACTIONS_EXACT_HTTPS_GET_R1",
      "raw_sha256_if_available":sha(body),
      "provider_native_hash_if_available":"",
      "text_extract_sha256":sha(text_bytes),
      "evidence_summary":f"{route['class_id']} exact explicit-locator/governance capture; route_basis={route['route_basis']}; P1 not assigned during acquisition.",
      "performance_outcomes_accessed":False,
      "configured_evidence_class":route["evidence_class"],
      "evidence_class_id":route["class_id"],
      "route_basis":route["route_basis"],
      "text_extract":readable,
      "explicit_urls":explicit_urls(readable),
      "explicit_locator_fields":locator_fields(readable),
      "p1_interpretation":"NOT_ASSIGNED_DURING_ACQUISITION"
    }

results=[]
for route in ROUTES:
    rec,body=fetch(route["url"])
    rr={k:route[k] for k in ["rank","repo","class_id","evidence_class","route_basis","url","evidence_type"]}
    rr["transport"]=rec
    rr["card"]=make_card(route,rec,body) if rec["terminal"]=="SUCCESS_CAPTURED" else None
    results.append(rr)

# Dynamic follow only for rank 5: C4 explicitly established default branch a8;
# if the exact branch-correct spec is captured, follow only URLs explicitly printed in it.
dynamic=[]
for rr in results:
    if rr["rank"]==5 and rr["class_id"]=="EC02" and rr["card"]:
        for lf in rr["card"]["explicit_locator_fields"]:
            for u in lf["urls"]:
                if "%{" in u: continue
                cls="EC06" if ("github.com/" in u or "gitlab.com/" in u) else "EC05" if ("metacpan.org/" in u or "hackage.haskell.org/" in u) else "EC04"
                et="EXPLICIT_LOCATOR_CANONICAL_REPOSITORY_CANDIDATE" if cls=="EC06" else "EXPLICIT_LOCATOR_OFFICIAL_REGISTRY_CANDIDATE" if cls=="EC05" else "EXPLICIT_LOCATOR_PROJECT_SITE_CANDIDATE"
                route={"rank":5,"repo":"src-anolis-os/sos","class_id":cls,
                       "evidence_class":{"EC04":"official project site/docs","EC05":"official project/distribution registry","EC06":"official canonical repository README/project docs"}[cls],
                       "route_basis":f"C5_EC02_EXPLICIT_{lf['field']}_FIELD","url":u,"evidence_type":et}
                rec,body=fetch(u)
                item={**route,"transport":rec,"card":make_card(route,rec,body) if rec["terminal"]=="SUCCESS_CAPTURED" else None}
                dynamic.append(item)
results.extend(dynamic)

payload={
 "protocol":"OMOSSP_PHASE_C5_EXPLICIT_LOCATOR_PROGRESS_CANARY_R1",
 "frozen_ranks":[1,2,3,5,6,9,10,11],
 "search_used":False,
 "name_similarity_inference_used":False,
 "performance_outcomes_accessed":False,
 "final_project_entity_id_minted":False,
 "p1_assigned_during_acquisition":False,
 "evidence_exhaustion_claimed":False,
 "results":results
}
canonical=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
pretty=json.dumps(payload,ensure_ascii=False,indent=2).encode()
(OUT/"c5_progression.json").write_bytes(pretty)
(OUT/"c5_canonical.sha256").write_text(sha(canonical)+"  canonical-json\n",encoding="utf-8")
print(json.dumps({"routes":len(results),"cards":sum(1 for r in results if r.get("card")),"canonical_sha256":sha(canonical)},indent=2))
