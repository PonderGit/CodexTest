"""R404 independent failure-seeking review of exact artifacts, not author summary."""
import json,pathlib,hashlib
root=pathlib.Path("collected")
def findone(p):
    xs=list(root.rglob(p))
    if len(xs)!=1:raise AssertionError((p,len(xs)))
    return xs[0]
def load(p):
    path=findone(p)
    return json.loads(path.read_text())
pre=load("R404_preexecution_source_manifest.json")
assert pre["selection_is_prior_r399_exact_two_ids"] is True
assert pre["official_bytes_sha256"]=="a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd"
expected={
"pylint":("pylint-dev__pylint-4661","1d1619ef913b99b06647d2030bddff4800abdf63","tests/lint/unittest_lint.py::test_pylint_home"),
"matplotlib":("matplotlib__matplotlib-26466","3dd06a46750d174f821df5377996f493f1af4ebb","lib/matplotlib/tests/test_text.py::test_annotate_and_offsetfrom_copy_input[png]")
}
assert {t["id"] for t in pre["tasks"]}=={v[0] for v in expected.values()}
out={"audit":"R404_INDEPENDENT_PASSB","basis":"original 6 job JSON + 3 recovery job JSON + earlier immutable source manifest","raw_statuses":{},"all_source_identities_reconciled":True,"full_official_grader_run":False}
for key,(id,base,test) in expected.items():
    out["raw_statuses"][key]={"original":{}}
    for arm in ("baseline","agent","gold"):
        s=load("R404_"+key+"_"+arm+".json")
        assert s["target"]==id and s["arm"]==arm and s["base"]==base and s["test_id"]==test
        p=s.get("pytest_exit")
        status=s.get("status")
        if status=="NATIVE_OFFICIAL_TEST_PASS":
            assert p==0 and any(c["argv"][:3]==["python","-m","pytest"] and c["exit"]==0 for c in s["commands"])
        if status=="NATIVE_OFFICIAL_TEST_FAIL":
            assert p==1 and any(c["argv"][:3]==["python","-m","pytest"] and c["exit"]==1 for c in s["commands"])
        if status=="INFRA_INSTALL_BLOCKED":
            assert p is None and any(c["argv"][:3]==["python","-m","pip"] and c["exit"]!=0 for c in s["commands"])
        out["raw_statuses"][key]["original"][arm]={"status":status,"pytest_exit":p}
    if key=="matplotlib":
        out["raw_statuses"][key]["recovery"]={}
        for arm in ("baseline","agent","gold"):
            s=load("RECOVERY_R404_matplotlib_"+arm+".json")
            assert s["target"]==id and s["arm"]==arm and s["base"]==base and s["test_id"]==test
            assert s.get("runtime_recovery")=="SYSTEM_FREETYPE_AND_QHULL_ONLY_NO_TEST_CHANGE"
            p=s.get("pytest_exit");status=s.get("status")
            if status=="NATIVE_OFFICIAL_TEST_PASS":
                assert p==0 and any(c["argv"][:3]==["python","-m","pytest"] and c["exit"]==0 for c in s["commands"])
            elif status=="NATIVE_OFFICIAL_TEST_FAIL":
                assert p==1 and any(c["argv"][:3]==["python","-m","pytest"] and c["exit"]==1 for c in s["commands"])
            else:
                assert status not in ("NATIVE_OFFICIAL_TEST_PASS","NATIVE_OFFICIAL_TEST_FAIL")
            out["raw_statuses"][key]["recovery"][arm]={"status":status,"pytest_exit":p}
o=out["raw_statuses"]["pylint"]["original"]
out["pylint_agent_data_path_supported"]=(o["agent"]["status"]=="NATIVE_OFFICIAL_TEST_FAIL")
out["pylint_gold_cache_pass_supported"]=(o["gold"]["status"]=="NATIVE_OFFICIAL_TEST_PASS")
out["scientific_interpretation"]="Actual native official test outcomes ONLY, no full SWE-bench grader, human adjudication, causal/algorithm originality or population inference. Q_issue remains UNKNOWN when two valid norm interpretations compete."
out["pylint_two_directory_types"]="Agent uses XDG data location, gold uses XDG cache: original official test tests cache-specific PR intent. Do not assert unique correct location."
out["blinded_human_coders"]=0
out["fixed_cohort_without_outcome_substitution"]=True
out["scope"]="G0, R403 tiered rubric only"
path=pathlib.Path("R404_PASSB_INDEPENDENT.json")
path.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
print(json.dumps(out,sort_keys=True,indent=2))
