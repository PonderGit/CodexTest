#!/usr/bin/env bash
set -euo pipefail
mkdir -p private evidence oracle
cat > oracle/sphinx_check.py <<'PY'
import runpy,ast,pathlib,json
s=runpy.run_path("/src/sphinx/sphinx/pycode/ast.py")
pairs=[("(1,)","(1,)"),("('alpha',)","('alpha',)"),("()","()"),("(1, 2)","(1, 2)")]
rows=[]
for src,expected in pairs:
    try:
        v=s["parse"](src).body[0].value
        actual=s["unparse"](v,src)
        node=ast.parse(actual,mode="eval").body
        rows.append({"input":src,"expected":expected,"observed":actual,
                     "lexical_pass":actual==expected,
                     "semantic_type_preserved":type(node).__name__==type(v).__name__,
                     "execution_error":None})
    except Exception as e:
        rows.append({"input":src,"expected":expected,"observed":None,
                     "lexical_pass":False,"semantic_type_preserved":False,
                     "execution_error":type(e).__name__})
pathlib.Path("/out/sphinx_raw.json").write_text(json.dumps(rows,indent=2)+"\n")
print(json.dumps(rows))
PY
cat > oracle/pylint_check.py <<'PY'
import os,subprocess,pathlib,json
cases=[
    ("override",{"PYLINTHOME":"/tmp/r399-override","XDG_CACHE_HOME":"/tmp/r399-xdg"},"/tmp/r399-override"),
    ("explicit_cache",{"XDG_CACHE_HOME":"/tmp/r399-xdg","HOME":"/tmp/r399-home"},"/tmp/r399-xdg/pylint"),
    ("linux_fallback",{"HOME":"/tmp/r399-home"},"/tmp/r399-home/.cache/pylint")
]
rows=[]
for label,envchanges,expected in cases:
    env=os.environ.copy()
    for k in ("PYLINTHOME","XDG_CACHE_HOME","HOME"):
        env.pop(k,None)
    env.update(envchanges)
    try:
        r=subprocess.run(["python","-c","from pylint import config; print(config.PYLINT_HOME)"],
                         cwd="/src/pylint",env=env,text=True,stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,timeout=45)
        got=r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        rows.append({"case":label,"expected":expected,"observed":got,
                     "returncode":r.returncode,"pass_pr_clause":got==expected and r.returncode==0,
                     "execution_error":None if r.returncode==0 else "MODULE_IMPORT_OR_RUNTIME_ERROR",
                     "stderr_tail":r.stderr[-240:]})
    except Exception as e:
        rows.append({"case":label,"expected":expected,"observed":None,
                     "returncode":None,"pass_pr_clause":False,
                     "execution_error":type(e).__name__})
pathlib.Path("/out/pylint_raw.json").write_text(json.dumps(rows,indent=2)+"\n")
print(json.dumps(rows))
PY
python3 - <<'PY'
import hashlib,pathlib,json
q={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pathlib.Path("oracle").glob("*.py")}
assert len(q)==2
pathlib.Path("evidence/R399_two_pilot_preregister.json").write_text(json.dumps({
 "scientific_scope":"fixed subset of preselected four tasks, not a new sample",
 "selected_cases":[{"id":"sphinx-doc__sphinx-9367","status":"historical resolved, model_name supplied"},
                   {"id":"pylint-dev__pylint-4661","status":"not listed resolved; row model_name missing"}],
 "excluded_cases_still_in_cohort":["django__django-12713","matplotlib__matplotlib-26466"],
 "method":"clean original source, genuine public agent patch, upstream developer gold; same prereg issue/PR checks",
 "Sphinx_issue_Q":"one-element tuple rendered with trailing comma, AST remains tuple, empty and multi-element tuple unchanged",
 "Pylint_Q_PR":"explicit PYLINTHOME overrides; XDG_CACHE_HOME default; Linux ~/.cache fallback",
 "Pylint_Q_issue":"UNKNOWN: issue refers to data vs PR to cache; no fabricated semantic error inference",
 "no_full_official_SWE_bench_regrade":True,"no_actual_PatchDiff_or_UTBoost_algorithm":True,
 "no_third_party_patch_redistribution":True,
 "check_source_sha256":q
},sort_keys=True,indent=2)+"\n")
PY
for KEY in sphinx pylint; do
  case "$KEY" in
    sphinx) URL=https://github.com/sphinx-doc/sphinx.git;BASE=6918e69600810a4664e53653d6ff0290c3c4a788 ;;
    pylint) URL=https://github.com/pylint-dev/pylint.git;BASE=1d1619ef913b99b06647d2030bddff4800abdf63 ;;
  esac
  mkdir -p "private/$KEY"
  git -C "private/$KEY" init -q
  git -C "private/$KEY" remote add origin "$URL"
  git -C "private/$KEY" fetch -q --depth=1 origin "$BASE"
  git -C "private/$KEY" checkout -q FETCH_HEAD
  test "$(git -C private/$KEY rev-parse HEAD)" = "$BASE"
done
python3 - <<'PY'
import pathlib,json,urllib.request,hashlib
cfg=[("sphinx","sphinx-doc/sphinx",9367,"sphinx/pycode/ast.py"),
     ("pylint","pylint-dev/pylint",4661,"pylint/config/__init__.py")]
for key,repo,n,path in cfg:
    url=f"https://api.github.com/repos/{repo}/pulls/{n}/files"
    r=urllib.request.Request(url,headers={"User-Agent":"TID-R399-PR-source-repro/1.0"})
    with urllib.request.urlopen(r,timeout=40) as x:rows=json.load(x)
    z=[y for y in rows if y.get("filename")==path]
    assert len(z)==1 and z[0].get("patch")
    patch="diff --git a/"+path+" b/"+path+"\n--- a/"+path+"\n+++ b/"+path+"\n"+z[0]["patch"]+"\n"
    pathlib.Path("private/"+key+"_gold.patch").write_text(patch)
PY
git -C private/sphinx apply --check "$GITHUB_WORKSPACE/private/sphinx_gold.patch"
git -C private/pylint apply --check "$GITHUB_WORKSPACE/private/pylint_gold.patch"
python3 - <<'PY'
import pathlib,json,urllib.request,hashlib
url="https://raw.githubusercontent.com/ZJU-CTAG/PatchDiff/0a8ed608f9f19396e1bb3f6f3dd88b0fb88b49d6/data/tool_results/20241221_codestory_midwit_claude-3-5-sonnet_swe-search/all_preds.jsonl"
wanted={"sphinx-doc__sphinx-9367":("sphinx","ea75242edd172a8d6698124d8fc016591e6d3f3a57b558e0f76e4cb3265a0596"),
        "pylint-dev__pylint-4661":("pylint","1dac958b775541fc85272270a8e27048cf354dd7b1431511ac86ad78145f453a")}
req=urllib.request.Request(url,headers={"User-Agent":"TID-R399-two-pilot-one-archive/1.0"})
found={}
with urllib.request.urlopen(req,timeout=55) as f:
    for line in f:
        o=json.loads(line)
        if o.get("instance_id") not in wanted:continue
        id=o["instance_id"]
        key,sha=wanted[id]
        patch=o["model_patch"]
        assert hashlib.sha256(patch.encode()).hexdigest()==sha and key not in found
        pathlib.Path("private/"+key+"_agent.patch").write_text(patch)
        found[key]={"task":id,"patch_sha256":sha,"row_model_name":o.get("model_name_or_path")}
assert len(found)==2
pathlib.Path("evidence/R399_agent_hash_manifest.json").write_text(json.dumps(found,indent=2)+"\n")
PY
git -C private/sphinx apply --check "$GITHUB_WORKSPACE/private/sphinx_agent.patch"
git -C private/pylint apply --check "$GITHUB_WORKSPACE/private/pylint_agent.patch"
cat > private/Dockerfile <<'EOF'
FROM python:3.9-slim-bookworm
RUN apt-get update -qq && apt-get install -y -qq git >/dev/null && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir -q 'pip<25' 'setuptools<70' wheel 'appdirs>=1.4.0'
COPY pylint/ /src/pylint/
RUN python -m pip install --no-cache-dir -q -e /src/pylint
COPY sphinx/ /src/sphinx/
WORKDIR /src
EOF
docker build -q -t tid-r399:two -f private/Dockerfile private > evidence/image_build.txt
docker image inspect tid-r399:two --format '{{.Id}}' > evidence/image_id.txt
for KEY in sphinx pylint; do
  for ARM in baseline agent gold; do
    mkdir -p "evidence/$KEY/$ARM"
    case "$ARM" in agent) PATCH="$KEY"_agent.patch;;gold) PATCH="$KEY"_gold.patch;;*) PATCH=none;;esac
    set +e
    timeout 90 docker run --rm --network none --cpus=1 --memory=2g --pids-limit=128 --cap-drop ALL --cap-add DAC_OVERRIDE --security-opt no-new-privileges \
      -v "$PWD/private:/private:ro" -v "$PWD/oracle:/oracle:ro" -v "$PWD/evidence/$KEY/$ARM:/out" \
      -e KEY="$KEY" -e PATCH="$PATCH" tid-r399:two /bin/sh -lc '
        set -e
        cd /src/"$KEY"
        if [ "$PATCH" != none ]; then git apply --check "/private/$PATCH";git apply "/private/$PATCH";fi
        python "/oracle/$KEY"_check.py >/out/stdout.txt 2>&1
        test -s "/out/$KEY"_raw.json || exit 63
      ' >"evidence/$KEY/$ARM/docker.log" 2>&1
    RC=$?
    set -e
    echo "$RC" > "evidence/$KEY/$ARM/docker_exit.txt"
  done
done
python3 - <<'PY'
import pathlib,json,hashlib
root=pathlib.Path("evidence")
report={"stage":"R399 two fixed prereg task checks","tasks":{}}
for key in ("sphinx","pylint"):
    report["tasks"][key]={}
    for arm in ("baseline","agent","gold"):
        d=root/key/arm
        raw=d/(key+"_raw.json")
        rc=d/"docker_exit.txt"
        out={"state":"NOT_VERIFIED","rows":[]}
        if raw.exists() and rc.exists() and rc.read_text().strip()=="0":
            data=json.loads(raw.read_text())
            out={"state":"VERIFIED_EXECUTED",
                 "rows":[{"test":x.get("input",x.get("case")),
                          "pass":x.get("lexical_pass",False) and x.get("semantic_type_preserved",False) if key=="sphinx" else x.get("pass_pr_clause"),
                          "error":x.get("execution_error")} for x in data],
                 "raw_sha256":hashlib.sha256(raw.read_bytes()).hexdigest()}
        report["tasks"][key][arm]=out
report["original_official_benchmark_regrade"]=False
report["other_competitor_algorithms_executed"]=[]
report["pylint_issue_truth"]="UNKNOWN (issue data dir versus PR cache dir)"
report["inference_boundary"]="two chosen runnable cases out of four preselected, no population or method effect estimate"
(root/"R399_two_task_report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
print(json.dumps(report,sort_keys=True,indent=2))
assert all(x["state"]=="VERIFIED_EXECUTED" for d in report["tasks"].values() for x in d.values()),"Fail closed on any missing raw behavior"
PY
sudo chown -R "$(id -u):$(id -g)" evidence
test ! -e evidence/agent.patch
