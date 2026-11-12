"""R406 independent failure seeking verification of firstparty 2024 human labels and model prompt provenance.
No new model runs, patch execution, or human judgments.
"""
import pathlib,json,hashlib,collections
ROOT=pathlib.Path("collected");OUT=pathlib.Path("evidence");OUT.mkdir(exist_ok=True)
def load(rel):
 p=ROOT/rel
 assert p.is_file(),str(p)
 return json.loads(p.read_text()),p
ann,pa=load("annotations/R406_original_verified_two_task_2024_annotations.json")
agent,pg=load("agent/R406_CodeStory_two_task_prompt_provenance_and_patch_features.json")
trace,pt=load("trace/R406_CodeStory_two_actual_public_trace_structure.json")
IDS=("pylint-dev__pylint-4661","matplotlib__matplotlib-26466")
assert ann["original_download_bytes"]==2397074
assert ann["original_zip_sha256"]=="b9297c31f6c2ef712218b5bb2830bd47a7f600dedf6b927191d0170177266ab9"
assert len(ann["matches"])==8
assert len([x for x in ann["archive_files"] if x["name"].endswith(".csv")])==2
assert set(agent["cases"])==set(trace["cases"])==set(IDS)
assert agent["source_archive_sha256"]=="74070d038a8dfb1e814f4f7bf6730c81643446688d4232b6553ecb93caa95bac"
out={"audit":"R406_PASS_B_INDEPENDENT","evidence_class_source":"VERIFIED_DIRECT",
     "interpretation_status":"DERIVED_WITH_MATERIAL_UNKNOWN","tasks":{},"error_scope":[],
     "original_2024_human_labels_existing_not_new_blind_raters":True,
     "published_OpenAI_2026_audit_per_case_membership":"NOT_VERIFIED",
     "original_model_exact_prompt_exposure":"NOT_VERIFIED",
     "full_official_grader_or_model_patch_run_now":False,
     "source_file_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (pa,pg,pt)}}
for id in IDS:
  rows=[x for x in ann["matches"] if id in x["ids"]]
  e=[x["row"] for x in rows if x["source"]=="ensembled_annotations_public.csv"]
  raw=[x["row"] for x in rows if x["source"]=="samples_with_3_annotations_public.csv"]
  assert len(e)==1 and len(raw)==3,(id,len(e),len(raw))
  ensemble=e[0]
  raters=sorted(raw,key=lambda x:x["user_id"])
  scores={
    "false_negative":[float(x["false_negative"]) for x in raters],
    "underspecified":[float(x["underspecified"]) for x in raters],
  }
  if id.startswith("pylint"):
    assert sorted(scores["false_negative"])==[0.0,0.0,1.0]
    assert sorted(scores["underspecified"])==[0.0,0.0,1.0]
    assert float(ensemble["false_negative"])==1
    assert float(ensemble["underspecified"])==1
    assert "another directory" in ensemble["false_negative_notes"]
    assert ensemble["filter_out"]=="False"
  else:
    assert all(x==0 for v in scores.values() for x in v)
    assert float(ensemble["false_negative"])==0
    assert float(ensemble["underspecified"])==0
    assert ensemble["filter_out"]=="False"
  c=agent["cases"][id];t=trace["cases"][id]
  assert c["original_archive_model_patch_sha256"]==(
    "1dac958b775541fc85272270a8e27048cf354dd7b1431511ac86ad78145f453a"
    if id.startswith("pylint") else "5897951ac9c2d7d87a875785274ac43d344bda846fdf7c4bf6d608718fd32e1f")
  assert t["sha256"]==(
    "264636693824002521a34f0f2eec40c2e5adb333e6bcda53a5e2daa33775dc6d"
    if id.startswith("pylint") else "bf75d0fc15f4311a03e0142e209bbef79783f05d8fe7e06a52dbfba704004c5f")
  assert t["log_is_complete_prompt_transcript"]=="NOT_VERIFIED"
  assert t["beginning_500chars"].startswith("=================================== START OF TRAJECTORY")
  assert t["first_12_line_prefixes"][1]=="MCTS Tree"
  assert c["public_trace_availability"]=="PUBLIC_KEY_EXISTS"
  assert c["s3_list_status"]=="PUBLIC_LIST_SUCCESS"
  out["tasks"][id]={
    "three_original_human_rater_ids":[x["user_id"] for x in raters],
    "three_original_human_scores":scores,
    "original_annotation_ensemble":{"false_negative":float(ensemble["false_negative"]),
       "underspecified":float(ensemble["underspecified"]),
       "filter_out":ensemble["filter_out"]},
    "original_annotation_direct_reported_notes":{
       "false_negative":ensemble["false_negative_notes"],
       "underspecified":ensemble["underspecified_notes"]},
    "model_patch_changed_files":c["changed_paths"],
    "model_patch_sha256":c["original_archive_model_patch_sha256"],
    "model_trace_sha256":t["sha256"],
    "model_trace_starts_with_MCTS_tree_not_complete_initial_prompt":True,
    "model_trace_contains_specific_historical_comment_strings":any(
        v["found"] for v in t["historical_discussion_markers"].values()),
    "prompt_hints_exposure":"NOT_VERIFIED_ACTUAL_PROMPT",
    "thirdparty_original_submission_readme_self_reports_no_hints":True,
    "issue_semantic_correctness":"NOT_VERIFIED",
  }
out["error_scope"].append("R404_Pylint_first_discovery_or_independent_novelty_claim blocked by already documented original 2024 human annotator disagreement")
out["error_scope"].append("R403_T1 source historical comments may contextualize analysis but do not define original benchmark visible prompt; primary 2024 annotator instructions explicitly exclude issue comments")
out["error_scope"].append("R404_Matplotlib agent patch touches _AnnotationBase but not OffsetFrom; no standalone T0 issue behavior execution or independent normative correctness established")
out["two_source_primary_competitors"]=["OpenAI 2024 three-human Verified curation with published per-case annotations",
                                    "OpenAI 2026 renewed six-plus-human review 138 targeted tasks (case membership NOT_VERIFIED)"]
path=OUT/"R406_PASSB_two_case_original_annotation_and_input_claim_boundaries.json"
path.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
print("PASS_B_TWO_TASKS",json.dumps({k:{q:v[q] for q in ("three_original_human_scores","original_annotation_ensemble","issue_semantic_correctness")} for k,v in out["tasks"].items()},ensure_ascii=False))
