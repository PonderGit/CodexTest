"""R406 two-target ONLY public CodeStory trace availability and patch semantic features.
No benchmark run; do not export original model patch or third-party traces.
"""
import urllib.request,urllib.error,urllib.parse,hashlib,json,pathlib,xml.etree.ElementTree as ET,re
ROOT=pathlib.Path("evidence");ROOT.mkdir(exist_ok=True)
IDS=["pylint-dev__pylint-4661","matplotlib__matplotlib-26466"]
ARCHIVE="https://raw.githubusercontent.com/ZJU-CTAG/PatchDiff/0a8ed608f9f19396e1bb3f6f3dd88b0fb88b49d6/data/tool_results/20241221_codestory_midwit_claude-3-5-sonnet_swe-search/all_preds.jsonl"
def fetch(url,limit=3000000):
  r=urllib.request.Request(url,headers={"User-Agent":"TID-R406-two-task-public-source-provenance/1.0"})
  with urllib.request.urlopen(r,timeout=35) as response:b=response.read(limit+1)
  assert len(b)<=limit
  return b
out={"audit":"R406_TARGETED_AGENT_INPUT_EVIDENCE_SOURCE_ONLY","cases":{},"archive":ARCHIVE,
"thirdparty_patch_raw_not_redistributed":True,"new_model_inference":False,"new_patch_execution":False}
b=fetch(ARCHIVE,2200000)
rows=[json.loads(x) for x in b.decode().splitlines() if x.strip()]
assert len(rows)==455
out["source_archive_sha256"]=hashlib.sha256(b).hexdigest()
expected={
"pylint-dev__pylint-4661":"1dac958b775541fc85272270a8e27048cf354dd7b1431511ac86ad78145f453a",
"matplotlib__matplotlib-26466":"5897951ac9c2d7d87a875785274ac43d344bda846fdf7c4bf6d608718fd32e1f"}
prefix_base="verified/20241221_codestory_midwit_claude-3-5-sonnet_swe-search/trajs/"
for id in IDS:
  r=[x for x in rows if x.get("instance_id")==id]
  assert len(r)==1
  model_patch=r[0]["model_patch"]
  assert hashlib.sha256(model_patch.encode()).hexdigest()==expected[id]
  out["cases"][id]={
   "original_archive_model_patch_sha256":expected[id],
   "row_level_model_name":r[0].get("model_name_or_path") or "NOT_VERIFIED",
   "changed_paths":[l.split(" b/",1)[1] for l in model_patch.splitlines() if l.startswith("diff --git a/")],
   "patch_added_lines_count":sum(l.startswith("+") and not l.startswith("+++") for l in model_patch.splitlines()),
   "patch_deleted_lines_count":sum(l.startswith("-") and not l.startswith("---") for l in model_patch.splitlines()),
   "data_storage_feature":{"uses_xdg_data_home":bool(re.search(r"XDG_DATA_HOME|user_data_dir|\.local/share",model_patch,re.I)),
       "uses_xdg_cache_home":bool(re.search(r"XDG_CACHE_HOME|user_cache_dir|\.cache",model_patch,re.I)),
       "uses_PYLINTHOME":("PYLINTHOME" in model_patch),
       "uses_appdirs":("appdirs" in model_patch)},
   "coordinate_feature":{"mentions_annotation_base":("_AnnotationBase" in model_patch),
       "mentions_offsetfrom":("OffsetFrom" in model_patch),
       "mentions_xy_coordinate":("self.xy" in model_patch)},
   "public_trace_availability":"NOT_VERIFIED"
  }
  prefix=prefix_base+id
  listing="https://swe-bench-submissions.s3.amazonaws.com/?"+urllib.parse.urlencode({"list-type":"2","prefix":prefix,"max-keys":40})
  try:
    raw=fetch(listing,160000)
    root=ET.fromstring(raw)
    keys=[(e.text or "") for e in root.iter() if e.tag.endswith("}Key") or e.tag=="Key"]
    keys=[k for k in keys if k.startswith(prefix)]
    out["cases"][id]["s3_list_status"]="PUBLIC_LIST_SUCCESS"
    out["cases"][id]["matching_object_keys"]=keys[:20]
    out["cases"][id]["public_trace_availability"]="PUBLIC_KEY_EXISTS" if keys else "NO_MATCHING_KEY_IN_PUBLIC_LIST"
    for key in keys[:3]:
      if key.endswith("/"):continue
      try:
        url="https://swe-bench-submissions.s3.amazonaws.com/"+urllib.parse.quote(key)
        obj=fetch(url,2000000)
        report={"key":key,"size":len(obj),"sha256":hashlib.sha256(obj).hexdigest(),
                "decoded_as_json":False,"contains_issue_core":False,"contains_hints":False,
                "initial_prompt":None}
        text=obj.decode("utf-8",errors="replace")
        report["contains_issue_core"]=(("XDG Base Directory Specification" in text) if id.startswith("pylint") else ("arrow position" in text))
        report["contains_hints"]=("OffsetFrom helper class" in text or "maybe present in the definition" in text)
        if text.lstrip().startswith(("{","[")):
          try:
            q=json.loads(text)
            report["decoded_as_json"]=True
            report["root_type"]=type(q).__name__
            report["root_keys"]=list(q.keys())[:25] if isinstance(q,dict) else []
            # only user/system prompts in first user 4k; ambiguous structures are not proof of exclusion
            report["root_preview_160"]=text[:160]
          except json.JSONDecodeError:pass
        out["cases"][id].setdefault("trace_inspection",[]).append(report)
      except Exception as e:
        out["cases"][id].setdefault("trace_inspection",[]).append({"key":key,"status":"NOT_VERIFIED","error":type(e).__name__+":"+str(e)[:120]})
  except Exception as e:
    out["cases"][id]["s3_list_status"]="NOT_VERIFIED"
    out["cases"][id]["s3_listing_error"]=type(e).__name__+":"+str(e)[:170]
p=ROOT/"R406_CodeStory_two_task_prompt_provenance_and_patch_features.json"
p.write_text(json.dumps(out,sort_keys=True,indent=2,ensure_ascii=False)+"\n")
print("SOURCE_ONLY",json.dumps(out,sort_keys=True,ensure_ascii=False)[:5000])
