#!/usr/bin/env python3
from __future__ import annotations
import base64, hashlib, html, json, os, re, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

UA="OMOSSP-C7-ProductionWorker/1.0"
BATCH=Path(os.environ.get("OMOSSP_BATCH_FILE","production_batches/omossp_c7_batch1.json"))
OUT=Path("omossp_c7_output")
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
    eid="E_C7_"+hashlib.sha256(f"{row['source_scale_rank']}|{class_id}|{url}|{sha(tb)}".encode()).hexdigest()[:24]
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
    cards=[]; attempts=[]; locators=[]; skipped_routes=[]
    repo=row["source_repo_name"]
    repo_url=f"https://gitee.com/{repo}"

    # EC01
    rec,body=fetch(repo_url)
    attempts.append({"class_id":"EC01","url":repo_url,"transport":rec})
    repo_text=""; default_branch="master"
    if rec["terminal"]=="SUCCESS_CAPTURED":
        ctype=rec["attempts"][-1].get("content_type")
        repo_text=decode(body,ctype)
        if ctype and "text/html" in ctype.lower(): repo_text=html_text(repo_text)
        default_branch=parse_default_branch(repo_text)
        cards.append(make_card(row,"EC01","exact source repository README/project docs","EXACT_SOURCE_REPOSITORY_PAGE",repo_url,rec,body,bounded(repo_text),f"EC01 exact source repository page; default_branch={default_branch}."))
        locators.extend(parse_repo_explicit_links(repo_text))
    if row.get("upstream_or_project_locator_raw"):
        locators.append({"origin":"FROZEN_AUTHORITY_LOCATOR","url":row["upstream_or_project_locator_raw"]})

    # EC02
    is_package=(row["source_container_class"] in PACKAGE_CLASSES or repo.startswith("src-openeuler/") or repo.startswith("src-anolis-"))
    if is_package:
        base=repo.rsplit("/",1)[-1]
        spec_url=f"https://gitee.com/{repo}/raw/{default_branch}/{base}.spec"
        rec2,b2=fetch(spec_url)
        attempts.append({"class_id":"EC02","url":spec_url,"transport":rec2})
        if rec2["terminal"]=="SUCCESS_CAPTURED":
            spec=decode(b2,rec2["attempts"][-1].get("content_type"))
            lines=[ln for ln in spec.splitlines() if re.match(r"^(Name|Version|URL|Homepage|HomePage|Source\\d*|VCS|SCM|Upstream|ProjectURL)\\s*:",ln.strip(),re.I)]
            extract="\\n".join(lines[:60])+"\\n\\n"+bounded(spec,900)
            spec_card=make_card(row,"EC02","exact package spec/source/homepage/VCS metadata","EXACT_PACKAGE_SPEC_METADATA",spec_url,rec2,b2,extract,"EC02 deterministic package spec capture; locators parsed only from explicit source-controlled fields.")
            cards.append(spec_card)
            for x in parse_macros_and_locators(spec):
                x["origin_card_id"]=spec_card["evidence_id"]
                locators.append(x)

    # Deduplicate explicit locators before any follow.
    seen=set(); dedup=[]
    for loc in locators:
        key=(loc.get("origin",""),loc.get("field",""),loc.get("url",""))
        if key not in seen:
            seen.add(key); dedup.append(loc)
    locators=dedup

    migrations={}
    githubs={}
    registries={}
    gitlabs={}
    project_sites={}

    for loc in locators:
        u=loc.get("url","").strip()
        if not u: continue
        p=urlparse(u)
        if p.scheme.lower()!="https":
            skipped_routes.append({"url":u,"origin":loc.get("origin",""),"reason":"UNQUALIFIED_NON_HTTPS_LOCATOR__NO_FETCH__NONTERMINAL"})
            continue
        if "atomgit.com/" in u:
            migrations[u]=loc
            continue
        gh=github_root(u)
        if gh:
            root,owner,name=gh
            d=githubs.setdefault(root,{"owner":owner,"name":name,"origins":[]})
            d["origins"].append(loc)
            continue
        reg=registry_kind(u)
        if reg:
            kind,ident=reg
            registries[(kind,ident)]={"kind":kind,"ident":ident,"origins":registries.get((kind,ident),{}).get("origins",[])+[loc]}
            continue
        host=p.netloc.lower()
        if host in {"invent.kde.org","gitlab.com"} or "gitlab" in host:
            gitlabs.setdefault(u.rstrip("/"),{"origins":[]})["origins"].append(loc)
            continue
        # Do not re-follow the same source repository as a project-site route.
        if u.rstrip("/")==repo_url.rstrip("/"):
            continue
        project_sites.setdefault(u,{"origins":[]})["origins"].append(loc)

    # EC03 provider-native upstream metadata
    gh_state={}
    for root in sorted(githubs):
        d=githubs[root]
        api=f"https://api.github.com/repos/{d['owner']}/{d['name']}"
        rr,bb=fetch(api); attempts.append({"class_id":"EC03","url":api,"transport":rr})
        meta_card=None; meta={}
        if rr["terminal"]=="SUCCESS_CAPTURED":
            ex=relevant_json_extract(bb,"github_meta")
            meta_card=make_card(row,"EC03","provider-native upstream metadata","GITHUB_PROVIDER_NATIVE_REPOSITORY_METADATA",api,rr,bb,ex,f"EC03 GitHub provider-native metadata derived from explicit locator {root}.")
            cards.append(meta_card)
            try: meta=json.loads(bb.decode())
            except Exception: meta={}
        gh_state[root]={"meta_card":meta_card,"meta":meta,"readme_card":None}

    # EC04 explicit project-site/docs candidates; HTTPS only.
    for u in sorted(project_sites):
        rr,bb=fetch(u); attempts.append({"class_id":"EC04","url":u,"transport":rr})
        if rr["terminal"]=="SUCCESS_CAPTURED":
            tx=decode(bb,rr["attempts"][-1].get("content_type"))
            if rr["attempts"][-1].get("content_type") and "text/html" in rr["attempts"][-1].get("content_type").lower(): tx=html_text(tx)
            cards.append(make_card(row,"EC04","official project site/docs","EXPLICIT_PROJECT_SITE_CANDIDATE",u,rr,bb,bounded(tx),f"EC04 exact HTTPS site route followed only from explicit source-controlled locator {u}; no P1 assigned from site access alone."))

    # EC05 official registry routes
    registry_state={}
    for kind,ident in sorted(registries):
        origins=registries[(kind,ident)]["origins"]
        card=None; valid=False
        if kind=="Hackage":
            ru=f"https://hackage.haskell.org/package/{ident}"
            rr,bb=fetch(ru); attempts.append({"class_id":"EC05","url":ru,"transport":rr})
            if rr["terminal"]=="SUCCESS_CAPTURED":
                tx=decode(bb,rr["attempts"][-1].get("content_type"))
                if rr["attempts"][-1].get("content_type") and "text/html" in rr["attempts"][-1].get("content_type").lower(): tx=html_text(tx)
                challenge=("Client Challenge" in tx or "JavaScript is disabled" in tx)
                card=make_card(row,"EC05","official project/distribution registry","HACKAGE_OFFICIAL_REGISTRY",ru,rr,bb,bounded(tx),f"EC05 Hackage registry route derived from explicit locator; challenge={challenge}.")
                cards.append(card)
                valid=(not challenge and re.search(r"(?mi)^\\s*"+re.escape(ident)+r"\\s*$",tx) is not None)
        elif kind=="MetaCPAN":
            ru=f"https://fastapi.metacpan.org/v1/release/{ident}"
            rr,bb=fetch(ru); attempts.append({"class_id":"EC05","url":ru,"transport":rr})
            if rr["terminal"]=="SUCCESS_CAPTURED":
                ex=relevant_json_extract(bb,"metacpan")
                card=make_card(row,"EC05","official project/distribution registry","METACPAN_PROVIDER_NATIVE_REGISTRY",ru,rr,bb,ex,"EC05 MetaCPAN provider-native registry route derived from explicit release locator.")
                cards.append(card)
                try:o=json.loads(bb.decode())
                except Exception:o={}
                valid=(o.get("distribution")==ident)
        elif kind=="PyPI":
            ru=f"https://pypi.org/pypi/{ident}/json"
            rr,bb=fetch(ru); attempts.append({"class_id":"EC05","url":ru,"transport":rr})
            if rr["terminal"]=="SUCCESS_CAPTURED":
                ex=relevant_json_extract(bb,"pypi")
                card=make_card(row,"EC05","official project/distribution registry","PYPI_PROVIDER_NATIVE_REGISTRY",ru,rr,bb,ex,"EC05 PyPI provider-native registry route derived from explicit project locator.")
                cards.append(card)
                try:o=json.loads(bb.decode())
                except Exception:o={}
                valid=(str(o.get("info",{}).get("name","")).casefold()==ident.casefold())
        registry_state[(kind,ident)]={"card":card,"valid":valid,"origins":origins}

    # EC06 canonical repository docs/pages
    for root in sorted(githubs):
        d=githubs[root]
        readme=f"https://api.github.com/repos/{d['owner']}/{d['name']}/readme"
        rr,bb=fetch(readme); attempts.append({"class_id":"EC06","url":readme,"transport":rr})
        if rr["terminal"]=="SUCCESS_CAPTURED":
            try:
                o=json.loads(bb.decode())
                tx=base64.b64decode(o.get("content","")).decode("utf-8",errors="replace") if o.get("encoding")=="base64" else decode(bb,rr["attempts"][-1].get("content_type"))
            except Exception:
                tx=decode(bb,rr["attempts"][-1].get("content_type"))
            c=make_card(row,"EC06","official canonical repository README/project docs","GITHUB_PROVIDER_NATIVE_README",readme,rr,bb,bounded(tx),f"EC06 project-controlled README from explicit GitHub locator {root}.")
            cards.append(c); gh_state[root]["readme_card"]=c

    gitlab_state={}
    for root in sorted(gitlabs):
        rr,bb=fetch(root); attempts.append({"class_id":"EC06","url":root,"transport":rr})
        c=None
        if rr["terminal"]=="SUCCESS_CAPTURED":
            tx=decode(bb,rr["attempts"][-1].get("content_type"))
            if rr["attempts"][-1].get("content_type") and "text/html" in rr["attempts"][-1].get("content_type").lower(): tx=html_text(tx)
            c=make_card(row,"EC06","official canonical repository README/project docs","EXPLICIT_GITLAB_PROJECT_PAGE",root,rr,bb,bounded(tx),f"EC06 exact GitLab-family project page from explicit locator {root}.")
            cards.append(c)
        gitlab_state[root]={"card":c,"origins":gitlabs[root]["origins"]}

    # EC07 migration/mirror/deprecation only after EC03-EC06
    for u in sorted(migrations):
        rr,bb=fetch(u); attempts.append({"class_id":"EC07","url":u,"transport":rr})
        if rr["terminal"]=="SUCCESS_CAPTURED":
            tx=decode(bb,rr["attempts"][-1].get("content_type"))
            if rr["attempts"][-1].get("content_type") and "text/html" in rr["attempts"][-1].get("content_type").lower(): tx=html_text(tx)
            cards.append(make_card(row,"EC07","official migration/mirror/deprecation notice","SOURCE_CONTAINER_MIGRATION_NOTICE",u,rr,bb,bounded(tx),"EC07 deduplicated explicit migration target followed from source-controlled evidence."))

    # EC08 governance/manifest last.
    if repo.startswith("openharmony/"):
        manifest="https://gitee.com/openharmony/manifest/raw/master/ohos/ohos.xml"
        rr,bb=fetch(manifest); attempts.append({"class_id":"EC08","url":manifest,"transport":rr})
        if rr["terminal"]=="SUCCESS_CAPTURED":
            tx=decode(bb,rr["attempts"][-1].get("content_type"))
            base=repo.split("/",1)[1]
            lines=[ln.strip() for ln in tx.splitlines() if base in ln or "<remote " in ln]
            cards.append(make_card(row,"EC08","official governance/manifest/release-note evidence","OPENHARMONY_OFFICIAL_MANIFEST",manifest,rr,bb,"\\n".join(lines[:30]),"EC08 official OpenHarmony manifest exact-name membership check; repository/component evidence only, never automatic theoretical project identity."))

    # Verify frozen class order among attempted routes.
    priority={"EC01":1,"EC02":2,"EC03":3,"EC04":4,"EC05":5,"EC06":6,"EC07":7,"EC08":8}
    seq=[priority[a["class_id"]] for a in attempts]
    if seq!=sorted(seq):
        raise RuntimeError(f"FROZEN_EVIDENCE_CLASS_ORDER_VIOLATION rank={row['source_scale_rank']} seq={seq}")

    proposals=[]
    for root,d in githubs.items():
        origins=d["origins"]; state=gh_state.get(root,{})
        meta=state.get("meta") or {}; readme_card=state.get("readme_card")
        if any(o.get("origin")=="EC02_SPEC_FIELD" for o in origins) and state.get("meta_card") and readme_card:
            if meta.get("fork") is False and str(meta.get("html_url","")).rstrip("/")==root.rstrip("/"):
                readme_card["evidence_grade"]="P1"
                proposals.append({"template":"T1_EXACT_PACKAGE_CONTROLLED_LOCATOR_PLUS_INDEPENDENT_PROJECT_CONTROLLED_P1","basis_type":"OFFICIAL_CANONICAL_REPOSITORY_SET","basis_value":root,"p1_card_id":readme_card["evidence_id"]})

    for (kind,ident),state in registry_state.items():
        if state["card"] and state["valid"] and any(o.get("origin")=="EC02_SPEC_FIELD" for o in state["origins"]):
            state["card"]["evidence_grade"]="P1"
            basis=f"{kind}:{ident}" if kind!="PyPI" else f"PyPI:{ident}"
            proposals.append({"template":"T5_OFFICIAL_PROJECT_REGISTRY_IDENTITY_WITH_EXACT_SOURCE_ROW_LOCATOR","basis_type":"OFFICIAL_PROJECT_REGISTRY_ID","basis_value":basis,"p1_card_id":state["card"]["evidence_id"]})

    for root,state in gitlab_state.items():
        if state["card"] and any(o.get("origin")=="EC02_SPEC_FIELD" for o in state["origins"]):
            state["card"]["evidence_grade"]="P1"
            proposals.append({"template":"T1_EXACT_PACKAGE_CONTROLLED_LOCATOR_PLUS_INDEPENDENT_PROJECT_CONTROLLED_P1","basis_type":"OFFICIAL_CANONICAL_REPOSITORY_SET","basis_value":root,"p1_card_id":state["card"]["evidence_id"]})

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
      "skipped_routes":skipped_routes,
      "decision_template":decision_template,
      "proposed":proposed,
      "evidence_exhaustion_eligible":False
    }

batch=json.loads(BATCH.read_text(encoding="utf-8"))
if batch.get("protocol")!="OMOSSP_PHASE_C7_PRODUCTION_BATCH1_FREEZE_R1":
    raise SystemExit("C7 batch protocol mismatch")
if batch.get("authority_sha256")!="22d5205d1d89a01d45eb682e1ef672c621c5fd455d07f810ee8cbc04e9ad9bc8":
    raise SystemExit("C7 authority SHA mismatch")
rows_all=batch.get("rows") or []
if len(rows_all)!=100:
    raise SystemExit(f"C7 batch row-count mismatch: {len(rows_all)}")
if len({int(r["source_scale_rank"]) for r in rows_all})!=100:
    raise SystemExit("C7 duplicate source_scale_rank")
if any(any("performance" in k.lower() for k in r.keys()) for r in rows_all):
    raise SystemExit("C7 performance field leakage into production batch")
canon_rows=json.dumps(rows_all,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
if sha(canon_rows)!=batch.get("membership_sha256"):
    raise SystemExit("C7 Batch-1 membership SHA mismatch")

shard=int(os.environ.get("OMOSSP_SHARD","1"))
if shard not in (1,2,3,4):
    raise SystemExit("C7 shard must be 1..4")
lo=(shard-1)*25
hi=lo+25
rows=rows_all[lo:hi]
if len(rows)!=25:
    raise SystemExit("C7 shard row-count mismatch")

results=[]
for row in rows:
    results.append(acquire(row))

payload={
 "protocol":"OMOSSP_PHASE_C7_PRODUCTION_SHARD_RESULT_R1",
 "batch_protocol":batch["protocol"],
 "selection_freeze_sha256":batch["selection_freeze_sha256"],
 "membership_sha256":batch["membership_sha256"],
 "authority_sha256":batch["authority_sha256"],
 "shard_index":shard,
 "shard_size":25,
 "batch_size":100,
 "position_range":[lo+1,hi],
 "search_used":False,
 "name_similarity_inference_used":False,
 "performance_outcomes_accessed":False,
 "final_project_entity_id_minted":False,
 "evidence_exhaustion_claimed":False,
 "case_specific_route_table_used":False,
 "checkpoint_state":"ACQUISITION_COMPLETE__RUNNER_REPLAY_PENDING",
 "results":results
}
canon=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
pretty=json.dumps(payload,ensure_ascii=False,indent=2).encode()
OUT.mkdir(exist_ok=True)
(OUT/f"c7_batch1_shard{shard}.json").write_bytes(pretty)
(OUT/f"c7_batch1_shard{shard}.sha256").write_text(sha(canon)+"  canonical-json\n",encoding="utf-8")
print(json.dumps({
 "batch":"B001",
 "shard":shard,
 "rows":len(results),
 "cards":sum(len(x["cards"]) for x in results),
 "auto_templates":sum(1 for x in results if x["decision_template"]),
 "human_gate_proposals":sum(1 for x in results if x["proposed"].get("human_gate_code")),
 "canonical_sha256":sha(canon)
},indent=2))

