"""Independent failure-seeking R404 source/raw-log verifier; no new test execution."""
import json,pathlib,hashlib
root=pathlib.Path("collected")
def read(group,filename):
  paths=list((root/group).rglob(filename))
  assert len(paths)==1,(group,filename,len(paths))
  return json.loads(paths[0].read_text()),paths[0]
pre,_=read("source","R404_preexecution_source_manifest.json")
assert pre["selection_is_prior_r399_exact_two_ids"] is True
assert pre["official_bytes_sha256"]=="a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd"
expect={
  "pylint":("pylint-dev__pylint-4661","1d1619ef913b99b06647d2030bddff4800abdf63","tests/lint/unittest_lint.py::test_pylint_home"),
  "matplotlib":("matplotlib__matplotlib-26466","3dd06a46750d174f821df5377996f493f1af4ebb","lib/matplotlib/tests/test_text.py::test_annotate_and_offsetfrom_copy_input[png]")
}
assert {x["id"] for x in pre["tasks"]}=={v[0] for v in expect.values()}
audit={"audit_id":"R404_INDEPENDENT_FAILURE_SEEKING_PASSB","experiment":"two previously selected tasks three source arms each",
       "official_original_dataset_sha256":pre["official_bytes_sha256"],
       "real_agent_row_model_name":"NOT_VERIFIED_ROW_LEVEL",
       "exact_original_swebench_grader_executed":False,"valid_original_official_image_environment_matplotlib":False,
       "human_independent_blind_coders":0,"sources":[],"cases":{}}
def validate(group,key,arm):
 id,base,test=expect[key]
 x,path=read(group,"R404_"+key+"_"+arm+".json")
 assert x["target"]==id and x["base"]==base and x["test_id"]==test and x["arm"]==arm
 cmds=x["commands"]
 assert any(c["argv"][:3]==["git","fetch","-q"] and c["exit"]==0 for c in cmds)
 assert any(c["argv"][:3]==["git","apply","--check"] and c["exit"]==0 for c in cmds)
 status=x["status"]; p=x.get("pytest_exit")
 tests=[c for c in cmds if c["argv"][:3]==["python","-m","pytest"]]
 if status=="NATIVE_OFFICIAL_TEST_PASS": assert p==0 and len(tests)==1 and tests[0]["exit"]==0 and test in tests[0]["argv"]
 elif status=="NATIVE_OFFICIAL_TEST_FAIL": assert p==1 and len(tests)==1 and tests[0]["exit"]==1 and test in tests[0]["argv"]
 elif status in ("INFRA_INSTALL_BLOCKED","TEST_INFRA_OR_COLLECTION_BLOCKED"): assert p is None or p not in (0,1)
 else: assert status!="NATIVE_OFFICIAL_TEST_PASS"
 audit["sources"].append({"name":str(path.relative_to(root)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
 return {"status":status,"pytest_exit":p,"runtime_recovery":x.get("runtime_recovery"),
   "pytest_stdout_tail":tests[0]["tail"][-500:] if tests else None}
for key in expect:
 audit["cases"][key]={"original":{}}
 for arm in ("baseline","agent","gold"):
  audit["cases"][key]["original"][arm]=validate("original",key,arm)
if True:
 audit["cases"]["matplotlib"]["recovery_1"]={a:validate("recovery1","matplotlib",a) for a in ("baseline","agent","gold")}
 audit["cases"]["matplotlib"]["compiler_baseline"]=validate("compiler","matplotlib","baseline")
 audit["cases"]["matplotlib"]["pyparsing_baseline"]=validate("canary","matplotlib","baseline")
 audit["cases"]["matplotlib"]["pyparsing_agent_gold"]={a:validate("pair","matplotlib",a) for a in ("agent","gold")}
assert audit["cases"]["pylint"]["original"]["baseline"]["status"]=="NATIVE_OFFICIAL_TEST_FAIL"
assert audit["cases"]["pylint"]["original"]["agent"]["status"]=="NATIVE_OFFICIAL_TEST_FAIL"
assert audit["cases"]["pylint"]["original"]["gold"]["status"]=="NATIVE_OFFICIAL_TEST_PASS"
assert audit["cases"]["matplotlib"]["original"]["baseline"]["status"]=="INFRA_INSTALL_BLOCKED"
assert audit["cases"]["matplotlib"]["pyparsing_baseline"]["status"]=="NATIVE_OFFICIAL_TEST_FAIL"
for arm in ("agent","gold"):
 r=audit["cases"]["matplotlib"]["pyparsing_agent_gold"][arm]
 assert r["runtime_recovery"]=="SYSTEM_FREETYPE_QHULL_AND_PYPARSING_3_0_9_NO_TEST_CHANGE"
pylint_agent,_=read("original","R404_pylint_agent.json")
assert any(".local/share/pylint" in c.get("tail","") and "/.cache/pylint" in c.get("tail","") for c in pylint_agent["commands"])
audit["pylint_agent_data_vs_gold_cache_difference_in_native_original_test"]=True
audit["reproducibility_boundary"]="Matplotlib native test reruns use system FreeType 2.13.2 vs project expected 2.6.1, not exact official SWE-bench grading image. Pylint native test uses Python 3.9, original base/patch/test and compatible deps."
audit["scientific_boundary"]="T0-T3 ambiguity persists; no verified task-correctness label, official scorer error rate, head-to-head published algorithm or Q1/Q2 novelty. Baseline, Agent, Gold outcomes not interchanged."
audit["fail_closed_under_infra_unknown"]=True
path=pathlib.Path("evidence/R404_PASSB_FINAL.json");path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(audit,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
print(json.dumps({k:v for k,v in audit.items() if k!="sources"},ensure_ascii=False,sort_keys=True,indent=2))
