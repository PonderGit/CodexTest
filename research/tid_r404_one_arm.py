"""R404 predeclared two cases x three arms; official test_patch & FAIL_TO_PASS only."""
import os,io,json,hashlib,urllib.request,pathlib,subprocess
import pyarrow.parquet as pq
key=os.environ["TARGET"]; arm=os.environ["ARM"]
cfg={
"pylint":("pylint-dev__pylint-4661","pylint-dev/pylint","1d1619ef913b99b06647d2030bddff4800abdf63","tests/lint/unittest_lint.py::test_pylint_home","1dac958b775541fc85272270a8e27048cf354dd7b1431511ac86ad78145f453a"),
"matplotlib":("matplotlib__matplotlib-26466","matplotlib/matplotlib","3dd06a46750d174f821df5377996f493f1af4ebb","lib/matplotlib/tests/test_text.py::test_annotate_and_offsetfrom_copy_input[png]","5897951ac9c2d7d87a875785274ac43d344bda846fdf7c4bf6d608718fd32e1f")
}
target,repo,base,test,expected_patch=cfg[key]
out=pathlib.Path("evidence");out.mkdir(exist_ok=True)
result={"target":target,"arm":arm,"base":base,"test_id":test,"kind":"NATIVE_OFFICIAL_TEST_NOT_ORIGINAL_SWEBENCH_GRADER","status":"NOT_VERIFIED","commands":[]}
def cmd(argv,cwd=None,timeout=450):
 try:
  p=subprocess.run(argv,cwd=cwd,timeout=timeout,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,errors="replace")
  result["commands"].append({"argv":argv,"exit":p.returncode,"tail":p.stdout[-9000:] if p.returncode else p.stdout[-600:]})
  return p.returncode,p.stdout
 except subprocess.TimeoutExpired:
  result["commands"].append({"argv":argv,"exit":124,"tail":"TIMEOUT"})
  return 124,"TIMEOUT"
def get(url,lim):
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"TID-R404-verified-two-cases/1.0"}),timeout=75) as f:b=f.read(lim+1)
 assert len(b)<=lim
 return b
def dig(s):return hashlib.sha256(s.encode()).hexdigest()
try:
 h="c104f840cc67f8b6eec6f759ebc8b2693d585d4a"
 blob=get("https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/resolve/"+h+"/data/test-00000-of-00001.parquet",2100000)
 assert len(blob)==2096679 and hashlib.sha256(blob).hexdigest()=="a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd"
 p=pq.ParquetFile(io.BytesIO(blob)); assert p.metadata.num_rows==500
 ids=p.read(columns=["instance_id"]).column(0).to_pylist()
 idx=[i for i,v in enumerate(ids) if v==target];assert len(idx)==1
 row=p.read().slice(idx[0],1).to_pylist()[0]
 assert row["repo"]==repo and row["base_commit"]==base and json.loads(row["FAIL_TO_PASS"])==[test]
 archive=get("https://raw.githubusercontent.com/ZJU-CTAG/PatchDiff/0a8ed608f9f19396e1bb3f6f3dd88b0fb88b49d6/data/tool_results/20241221_codestory_midwit_claude-3-5-sonnet_swe-search/all_preds.jsonl",2200000)
 pred=[json.loads(s) for s in archive.decode().splitlines() if s.strip()]
 matches=[v for v in pred if v["instance_id"]==target];assert len(matches)==1
 assert dig(matches[0]["model_patch"])==expected_patch
 code,logs=cmd(["git","init","-q","src"]);assert code==0
 cmd(["git","remote","add","origin","https://github.com/"+repo+".git"],cwd="src")
 code,logs=cmd(["git","fetch","-q","--depth=1","origin",base],cwd="src",timeout=200);assert code==0
 code,logs=cmd(["git","checkout","-q","FETCH_HEAD"],cwd="src");assert code==0
 for ptext,name in ([(matches[0]["model_patch"],"agent.patch")] if arm=="agent" else [(row["patch"],"gold.patch")] if arm=="gold" else []):
  pathlib.Path(name).write_text(ptext)
  code,logs=cmd(["git","apply","--check","../"+name],cwd="src");assert code==0
  code,logs=cmd(["git","apply","../"+name],cwd="src");assert code==0
 pathlib.Path("official_test.patch").write_text(row["test_patch"])
 code,logs=cmd(["git","apply","--check","../official_test.patch"],cwd="src");assert code==0
 code,logs=cmd(["git","apply","../official_test.patch"],cwd="src");assert code==0
 result["status"]="PATCH_AND_TEST_APPLIED"
 if key=="matplotlib":
  code,logs=cmd(["sudo","apt-get","update","-qq"],timeout=180)
  assert code==0
  code,logs=cmd(["sudo","apt-get","install","-y","-qq","libfreetype6-dev","libpng-dev","libqhull-dev","pkg-config"],timeout=180)
  assert code==0
  code,logs=cmd(["python","-m","pip","install","-q","numpy==1.26.4","pyparsing==3.0.9","setuptools<70","setuptools_scm<9","wheel","pybind11<3","Cython<3","meson-python<0.17","pytest==7.4.4"],timeout=180)
 else:code,logs=cmd(["python","-m","pip","install","-q","appdirs==1.4.4","pytest==7.4.4","setuptools<70","wheel"],timeout=180)
 assert code==0
 if key=="matplotlib":
  pathlib.Path("src/mplsetup.cfg").write_text("[libs]\nsystem_freetype = True\nsystem_qhull = True\n")
  result["runtime_recovery"]="SYSTEM_FREETYPE_QHULL_AND_PYPARSING_3_0_9_NO_TEST_CHANGE"
 code,logs=cmd(["python","-m","pip","install","--no-build-isolation","-e","."],cwd="src",timeout=500)
 if code:result["status"]="INFRA_INSTALL_BLOCKED"
 else:
  code,logs=cmd(["python","-m","pytest","-q",test,"--tb=short","-rA"],cwd="src",timeout=180)
  result["status"]="NATIVE_OFFICIAL_TEST_PASS" if code==0 else "NATIVE_OFFICIAL_TEST_FAIL" if code==1 else "TEST_INFRA_OR_COLLECTION_BLOCKED"
  result["pytest_exit"]=code
except Exception as e:
 result["error"]=type(e).__name__+": "+str(e)[:300]
 if result["status"]=="NOT_VERIFIED":result["status"]="SOURCE_OR_PATCH_BLOCKED"
 elif result["status"]=="PATCH_AND_TEST_APPLIED":result["status"]="INFRA_INSTALL_BLOCKED"
finally:
 out.joinpath("R404_"+key+"_"+arm+".json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
 print("R404_RESULT",json.dumps({k:v for k,v in result.items() if k!="commands"},sort_keys=True))
