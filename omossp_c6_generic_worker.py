#!/usr/bin/env python3
from __future__ import annotations
import base64, hashlib, html, json, re, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

UA="OMOSSP-C6-GenericWorker/1.0"
PILOT=Path("omossp_c6_pilot.json")
OUT=Path("omossp_c6_output")
OUT.mkdir(exist_ok=True)

PACKAGE_CLASSES={"PACKAGE_CONTAINER","UNRESOLVED_SOURCE_CONTAINER"}
AUTO_ACCEPT={
"T1_EXACT_PACKAGE_CONTROLLED_LOCATOR_PLUS_INDEPENDENT_PROJECT_CONTROLLED_P1",
"T2_PROVIDER_NATIVE_UPSTREAM_METADATA_PLUS_INDEPENDENT_PROJECT_CONTROLLED_P1",
"T3_OFFICIAL_PROJECT_REGISTRY_MIGRATION_PLUS_CURRENT_PROJECT_CONTROLLED_CONFIRMATION",
"T4_DIRECT_REPOSITORY_EXPLICIT_PROJECT_SCOPE_PLUS_SECOND_PROJECT_CONTROLLED_CORROBORATION",
"T5_OFFICIAL_PROJECT_REGISTRY_IDENTITY_WITH_EXACT_SOURCE_ROW_LOCATOR",
}

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
                rec["terminal"]="SUCCESS_CAPTURED"
                return rec,body
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

def decode(body:bytes,ctype:str|None)->str:
    if ctype and "application/json" in ctype.lower():
        try: return json.dumps(json.loads(body.decode("utf-8")),ensure_ascii=False,indent=2)
        except Exception: pass
    return body.decode("utf-8",errors="replace").replace("\r\n","\n").replace("\r","\n")

def html_text(s:str)->str:
    s=re.sub(r"(?is)<script.*?>.*?</script>"," ",s)
    s=re.sub(r"(?is)<style.*?>.*?</style>"," ",s)
    s=re.sub(r"(?s)<[^>]+>","\n",s)
    s=html.unescape(s)
    s=re.sub(r"\n[ \t]+","\n",s)
    s=re.sub(r"\n{3,}","\n\n",s)
    return s.strip()

def bounded(text:str,n=1600)->str:
    return text[:n]

def make_card(row,class_id,evidence_class,evidence_type,url,rec,body,extract:str,summary:str):
    tb=extract.encode("utf-8")
    eid="E_C6_"+hashlib.sha256(f"{row['source_scale_rank']}|{class_id}|{url}|{sha(tb)}".encode()).hexdigest()[:24]
    return {
      "evidence_id":eid,
      "source_scale_rank":row["source_scale_rank"],
      "source_repo_name":row["source_repo_name"],
      "evidence_grade":"P2",
      "evidence_type":evidence_type,
      "source_url":url,
      "retrieved_at_utc":nowz(),
      "capture_method":"GITHUB_ACTIONS_EXACT_HTTPS_GET_R1",
      "raw_sha256_if_available":sha(body),
      "provider_native_hash_if_available":"",
      "text_extract_sha256":sha(tb),
      "evidence_summary":summary,
      "performance_outcomes_accessed":False,
      "configured_evidence_class":evidence_class,
      "evidence_class_id":class_id,
      "text_extract":extract
    }

def parse_default_branch(text:str)->str:
    m=re.search(r"\*\*Default Branch\*\*:\s*([^\s]+)",text,re.I)
    if not m: m=re.search(r"Default Branch\s*:\s*([^\s]+)",text,re.I)
    return m.group(1).strip() if m else "master"

def parse_repo_explicit_links(text:str):
    out=[]
    for line in text.splitlines():
        line=line.strip()
        if "migrat" in line.lower() or "迁移" in line or "Linked:" in line or "Homepage" in line:
            for u in re.findall(r"https?://[^\s<>'\"\)\]]+",line):
                out.append({"origin":"EC01_REPO_DOC","url":u.rstrip(".,")})
    return out

def parse_macros_and_locators(text:str):
    macros={}
    for line in text.splitlines():
        m=re.match(r"^%(?:global|define)\s+([A-Za-z0-9_]+)\s+(.+?)\s*$",line.strip())
        if m: macros[m.group(1)]=m.group(2).strip()
    field_re=re.compile(r"^(URL|Homepage|HomePage|Source\d*|VCS|SCM|Upstream|ProjectURL)\s*:\s*(.+)$",re.I)
    rows=[]
    for line in text.splitlines():
        m=field_re.match(line.strip())
        if not m: continue
        value=m.group(2).strip()
        prev=None
        for _ in range(8):
            if value==prev: break
            prev=value
            for k,v in macros.items(): value=value.replace("%{"+k+"}",v)
        urls=re.findall(r"https?://[^\s<>'\"\)\]]+",value)
        for u in urls:
            if "%{" not in u:
                rows.append({"origin":"EC02_SPEC_FIELD","field":m.group(1),"url":u.rstrip(".,")})
    return rows

def github_root(url:str):
    p=urlparse(url)
    if p.netloc.lower() not in {"github.com","www.github.com"}: return None
    parts=[x for x in p.path.split("/") if x]
    if len(parts)<2: return None
    owner,repo=parts[0],parts[1]
    if repo.endswith(".git"): repo=repo[:-4]
    return f"https://github.com/{owner}/{repo}",owner,repo

def registry_kind(url:str):
    p=urlparse(url); h=p.netloc.lower(); parts=[x for x in p.path.split("/") if x]
    if h.endswith("hackage.haskell.org") and len(parts)>=2 and parts[0]=="package":
        return ("Hackage",parts[1])
    if h.endswith("metacpan.org") and len(parts)>=2 and parts[0]=="release":
        return ("MetaCPAN",parts[1])
    if h in {"pypi.org","www.pypi.org"} and len(parts)>=2 and parts[0]=="project":
        return ("PyPI",parts[1])
    if h=="pypi.python.org" and len(parts)>=2 and parts[0]=="pypi":
        return ("PyPI",parts[1])
    return None

def relevant_json_extract(body:bytes,kind:str)->str:
    try: o=json.loads(body.decode("utf-8"))
    except Exception: return bounded(body.decode("utf-8",errors="replace"))
    if kind=="github_meta":
        keep={k:o.get(k) for k in ["full_name","html_url","description","fork","homepage","archived","disabled","default_branch"] if k in o}
        return json.dumps(keep,ensure_ascii=False,indent=2)
    if kind=="pypi":
        info=o.get("info",{})
        keep={"name":info.get("name"),"version":info.get("version"),"home_page":info.get("home_page"),"project_urls":info.get("project_urls")}
        return json.dumps(keep,ensure_ascii=False,indent=2)
    if kind=="metacpan":
        keep={k:o.get(k) for k in ["distribution","name","version","author","resources"] if k in o}
        return json.dumps(keep,ensure_ascii=False,indent=2)
    return bounded(json.dumps(o,ensure_ascii=False,indent=2))

def acquire(row):
    cards=[]; attempts=[]; locators=[]
    repo=row["source_repo_name"]
    repo_url=f"https://gitee.com/{repo}"
    rec,body=fetch(repo_url); attempts.append({"class_id":"EC01","url":repo_url,"transport":rec})
    repo_text=""
    default_branch="master"
    if rec["terminal"]=="SUCCESS_CAPTURED":
        ctype=rec["attempts"][-1].get("content_type")
        repo_text=decode(body,ctype)
        if ctype and "text/html" in ctype.lower(): repo_text=html_text(repo_text)
        default_branch=parse_default_branch(repo_text)
        ex=bounded(repo_text)
        cards.append(make_card(row,"EC01","exact source repository README/project docs","EXACT_SOURCE_REPOSITORY_PAGE",repo_url,rec,body,ex,f"EC01 exact source repository page; default_branch={default_branch}."))
        locators.extend(parse_repo_explicit_links(repo_text))
    if row.get("upstream_or_project_locator_raw"):
        locators.append({"origin":"FROZEN_AUTHORITY_LOCATOR","url":row["upstream_or_project_locator_raw"]})

    is_package=(row["source_container_class"] in PACKAGE_CLASSES or repo.startswith("src-openeuler/") or repo.startswith("src-anolis-"))
    if is_package:
        base=repo.rsplit("/",1)[-1]
        spec_url=f"https://gitee.com/{repo}/raw/{default_branch}/{base}.spec"
        rec2,b2=fetch(spec_url); attempts.append({"class_id":"EC02","url":spec_url,"transport":rec2})
        if rec2["terminal"]=="SUCCESS_CAPTURED":
            spec=decode(b2,rec2["attempts"][-1].get("content_type"))
            lines=[ln for ln in spec.splitlines() if re.match(r"^(Name|Version|URL|Homepage|HomePage|Source\d*|VCS|SCM|Upstream|ProjectURL)\s*:",ln.strip(),re.I)]
            extract="\n".join(lines[:60])+"\n\n"+bounded(spec,900)
            card=make_card(row,"EC02","exact package spec/source/homepage/VCS metadata","EXACT_PACKAGE_SPEC_METADATA",spec_url,rec2,b2,extract,"EC02 deterministic package spec capture; locators parsed only from explicit source-controlled fields.")
            cards.append(card)
            for x in parse_macros_and_locators(spec):
                x["origin_card_id"]=card["evidence_id"]; locators.append(x)

    # Explicit migration links from EC01.
    for loc in list(locators):
        u=loc["url"]
        if "atomgit.com/" in u:
            recx,bx=fetch(u); attempts.append({"class_id":"EC07","url":u,"transport":recx})
            if recx["terminal"]=="SUCCESS_CAPTURED":
                tx=decode(bx,recx["attempts"][-1].get("content_type"))
                if recx["attempts"][-1].get("content_type") and "text/html" in recx["attempts"][-1].get("content_type").lower(): tx=html_text(tx)
                cards.append(make_card(row,"EC07","official migration/mirror/deprecation notice","SOURCE_CONTAINER_MIGRATION_NOTICE",u,recx,bx,bounded(tx),"EC07 explicit migration target followed from source-controlled evidence."))

    # Provider/registry dispatch from explicit locators only.
    dispatched=set()
    proposals=[]
    for loc in list(locators):
        u=loc["url"]; origin=loc.get("origin","")
        gh=github_root(u)
        if gh:
            root,owner,name=gh
            if root in dispatched: continue
            dispatched.add(root)
            api=f"https://api.github.com/repos/{owner}/{name}"
            reca,ba=fetch(api); attempts.append({"class_id":"EC03","url":api,"transport":reca})
            meta_card=None
            if reca["terminal"]=="SUCCESS_CAPTURED":
                ex=relevant_json_extract(ba,"github_meta")
                meta_card=make_card(row,"EC03","provider-native upstream metadata","GITHUB_PROVIDER_NATIVE_REPOSITORY_METADATA",api,reca,ba,ex,f"EC03 GitHub provider-native metadata derived from explicit locator {root}.")
                cards.append(meta_card)
            readme=f"https://api.github.com/repos/{owner}/{name}/readme"
            recr,br=fetch(readme); attempts.append({"class_id":"EC06","url":readme,"transport":recr})
            readme_card=None
            if recr["terminal"]=="SUCCESS_CAPTURED":
                try:
                    o=json.loads(br.decode()); txt=base64.b64decode(o.get("content","")).decode("utf-8",errors="replace") if o.get("encoding")=="base64" else decode(br,recr["attempts"][-1].get("content_type"))
                except Exception: txt=decode(br,recr["attempts"][-1].get("content_type"))
                readme_card=make_card(row,"EC06","official canonical repository README/project docs","GITHUB_PROVIDER_NATIVE_README",readme,recr,br,bounded(txt),f"EC06 project-controlled README from explicit GitHub locator {root}.")
                cards.append(readme_card)
            if origin=="EC02_SPEC_FIELD" and meta_card and readme_card:
                try: meta=json.loads(ba.decode())
                except Exception: meta={}
                if meta.get("fork") is False and meta.get("html_url","").rstrip("/")==root.rstrip("/"):
                    readme_card["evidence_grade"]="P1"
                    proposals.append({
                      "template":"T1_EXACT_PACKAGE_CONTROLLED_LOCATOR_PLUS_INDEPENDENT_PROJECT_CONTROLLED_P1",
                      "basis_type":"OFFICIAL_CANONICAL_REPOSITORY_SET","basis_value":root,
                      "p1_card_id":readme_card["evidence_id"]
                    })
            continue

        reg=registry_kind(u)
        if reg:
            kind,ident=reg; key=f"{kind}:{ident}"
            if key in dispatched: continue
            dispatched.add(key)
            if kind=="Hackage":
                ru=f"https://hackage.haskell.org/package/{ident}"
                rr,bb=fetch(ru); attempts.append({"class_id":"EC05","url":ru,"transport":rr})
                if rr["terminal"]=="SUCCESS_CAPTURED":
                    tx=decode(bb,rr["attempts"][-1].get("content_type"))
                    if rr["attempts"][-1].get("content_type") and "text/html" in rr["attempts"][-1].get("content_type").lower(): tx=html_text(tx)
                    challenge=("Client Challenge" in tx or "JavaScript is disabled" in tx)
                    card=make_card(row,"EC05","official project/distribution registry","HACKAGE_OFFICIAL_REGISTRY",ru,rr,bb,bounded(tx),f"EC05 Hackage registry route derived from explicit locator; challenge={challenge}.")
                    cards.append(card)
                    if origin=="EC02_SPEC_FIELD" and not challenge and re.search(r"(?mi)^\s*"+re.escape(ident)+r"\s*$",tx):
                        card["evidence_grade"]="P1"
                        proposals.append({"template":"T5_OFFICIAL_PROJECT_REGISTRY_IDENTITY_WITH_EXACT_SOURCE_ROW_LOCATOR","basis_type":"OFFICIAL_PROJECT_REGISTRY_ID","basis_value":f"Hackage:{ident}","p1_card_id":card["evidence_id"]})
            elif kind=="MetaCPAN":
                ru=f"https://fastapi.metacpan.org/v1/release/{ident}"
                rr,bb=fetch(ru); attempts.append({"class_id":"EC05","url":ru,"transport":rr})
                if rr["terminal"]=="SUCCESS_CAPTURED":
                    ex=relevant_json_extract(bb,"metacpan")
                    card=make_card(row,"EC05","official project/distribution registry","METACPAN_PROVIDER_NATIVE_REGISTRY",ru,rr,bb,ex,"EC05 MetaCPAN provider-native registry route derived from explicit release locator.")
                    cards.append(card)
                    try:o=json.loads(bb.decode())
                    except Exception:o={}
                    if origin=="EC02_SPEC_FIELD" and o.get("distribution")==ident:
                        card["evidence_grade"]="P1"
                        proposals.append({"template":"T5_OFFICIAL_PROJECT_REGISTRY_IDENTITY_WITH_EXACT_SOURCE_ROW_LOCATOR","basis_type":"OFFICIAL_PROJECT_REGISTRY_ID","basis_value":f"MetaCPAN:{ident}","p1_card_id":card["evidence_id"]})
            elif kind=="PyPI":
                ru=f"https://pypi.org/pypi/{ident}/json"
                rr,bb=fetch(ru); attempts.append({"class_id":"EC05","url":ru,"transport":rr})
                if rr["terminal"]=="SUCCESS_CAPTURED":
                    ex=relevant_json_extract(bb,"pypi")
                    card=make_card(row,"EC05","official project/distribution registry","PYPI_PROVIDER_NATIVE_REGISTRY",ru,rr,bb,ex,"EC05 PyPI provider-native registry route derived from explicit project locator.")
                    cards.append(card)
                    try:o=json.loads(bb.decode())
                    except Exception:o={}
                    if origin=="EC02_SPEC_FIELD" and str(o.get("info",{}).get("name","")).casefold()==ident.casefold():
                        card["evidence_grade"]="P1"
                        proposals.append({"template":"T5_OFFICIAL_PROJECT_REGISTRY_IDENTITY_WITH_EXACT_SOURCE_ROW_LOCATOR","basis_type":"OFFICIAL_PROJECT_REGISTRY_ID","basis_value":f"PyPI:{o['info']['name']}","p1_card_id":card["evidence_id"]})
            continue

        p=urlparse(u)
        host=p.netloc.lower()
        if host in {"invent.kde.org","gitlab.com"} or "gitlab" in host:
            root=u.rstrip("/")
            if root in dispatched: continue
            dispatched.add(root)
            rr,bb=fetch(root); attempts.append({"class_id":"EC06","url":root,"transport":rr})
            if rr["terminal"]=="SUCCESS_CAPTURED":
                tx=decode(bb,rr["attempts"][-1].get("content_type"))
                if rr["attempts"][-1].get("content_type") and "text/html" in rr["attempts"][-1].get("content_type").lower(): tx=html_text(tx)
                card=make_card(row,"EC06","official canonical repository README/project docs","EXPLICIT_GITLAB_PROJECT_PAGE",root,rr,bb,bounded(tx),f"EC06 exact GitLab-family project page from explicit locator {root}.")
                cards.append(card)
                if origin=="EC02_SPEC_FIELD":
                    card["evidence_grade"]="P1"
                    proposals.append({"template":"T1_EXACT_PACKAGE_CONTROLLED_LOCATOR_PLUS_INDEPENDENT_PROJECT_CONTROLLED_P1","basis_type":"OFFICIAL_CANONICAL_REPOSITORY_SET","basis_value":root,"p1_card_id":card["evidence_id"]})
            continue

    # OpenHarmony official manifest is a frozen EC08 governance route, never automatic P1.
    if repo.startswith("openharmony/"):
        manifest="https://gitee.com/openharmony/manifest/raw/master/ohos/ohos.xml"
        rr,bb=fetch(manifest); attempts.append({"class_id":"EC08","url":manifest,"transport":rr})
        if rr["terminal"]=="SUCCESS_CAPTURED":
            tx=decode(bb,rr["attempts"][-1].get("content_type"))
            base=repo.split("/",1)[1]
            lines=[ln.strip() for ln in tx.splitlines() if base in ln or "<remote " in ln]
            ex="\n".join(lines[:30])
            cards.append(make_card(row,"EC08","official governance/manifest/release-note evidence","OPENHARMONY_OFFICIAL_MANIFEST",manifest,rr,bb,ex,"EC08 official OpenHarmony manifest exact-name membership check; repository/component evidence only, never automatic theoretical project identity."))

    # Deduplicate proposals conservatively.
    uniq={}
    for p in proposals: uniq[(p["basis_type"],p["basis_value"])]=p
    vals=list(uniq.values())
    if len(vals)==1:
        p=vals[0]
        decision_template=p["template"]
        proposed={"entity_identity_basis_type":p["basis_type"],"entity_identity_basis_value":p["basis_value"],"human_gate_code":""}
    elif len(vals)>1:
        decision_template=None
        proposed={"human_gate_code":"HG02_CONFLICTING_DECISION_GRADE_P1_EVIDENCE"}
    else:
        decision_template=None
        proposed={}

    return {
      "source_row":row,
      "cards":cards,
      "attempts":attempts,
      "explicit_locators":locators,
      "decision_template":decision_template,
      "proposed":proposed,
      "evidence_exhaustion_eligible":False
    }

pilot=json.loads(PILOT.read_text())
rows=pilot["rows"]
if len(rows)!=24 or len({int(r["source_scale_rank"]) for r in rows})!=24:
    raise SystemExit("C6 pilot integrity failure")
if any("performance" in k.lower() for r in rows for k in r.keys()):
    raise SystemExit("performance field present in pilot input")

results=[]
for row in rows:
    results.append(acquire(row))

payload={
 "protocol":"OMOSSP_PHASE_C6_GENERIC_EVIDENCE_PROGRESSION_PILOT_R1",
 "pilot_sha256":pilot["pilot_sha256"],
 "authority_sha256":pilot["authority_sha256"],
 "pilot_rows":len(rows),
 "search_used":False,
 "name_similarity_inference_used":False,
 "performance_outcomes_accessed":False,
 "final_project_entity_id_minted":False,
 "evidence_exhaustion_claimed":False,
 "case_specific_route_table_used":False,
 "results":results
}
canon=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
pretty=json.dumps(payload,ensure_ascii=False,indent=2).encode()
(OUT/"c6_pilot_result.json").write_bytes(pretty)
(OUT/"c6_pilot_result.sha256").write_text(sha(canon)+"  canonical-json\n",encoding="utf-8")
print(json.dumps({
 "rows":len(results),
 "cards":sum(len(x["cards"]) for x in results),
 "auto_templates":sum(1 for x in results if x["decision_template"]),
 "human_gate_proposals":sum(1 for x in results if x["proposed"].get("human_gate_code")),
 "canonical_sha256":sha(canon)
},indent=2))
