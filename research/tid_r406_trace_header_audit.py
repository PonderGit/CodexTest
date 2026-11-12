"""R406 inspect ONLY actual published CodeStory trajectory headers and issue-text exposure.
The public original log bytes are fingerprinted but never archived or redistributed.
"""
import urllib.request, urllib.parse, pathlib,hashlib,json,re
P="verified/20241221_codestory_midwit_claude-3-5-sonnet_swe-search/trajs/"
cases={
 "pylint-dev__pylint-4661":{
  "key":P+"pylint-dev__pylint-4661.log",
  "sha256":"264636693824002521a34f0f2eec40c2e5adb333e6bcda53a5e2daa33775dc6d",
  "main_phrases":["Make pylint XDG Base Directory Specification compliant","$HOME/.local/share","I have this really annoying"],
  "history_phrases":["I wonder if it shouldn't use", "maybe we could change this default value"]},
 "matplotlib__matplotlib-26466":{
  "key":P+"matplotlib__matplotlib-26466.log",
  "sha256":"bf75d0fc15f4311a03e0142e209bbef79783f05d8fe7e06a52dbfba704004c5f",
  "main_phrases":["Updating an array passed as the xy parameter","Both arrows should be horizontal","changing the array after calling"],
  "history_phrases":["A similar issue is maybe present in the definition of OffsetFrom","OffsetFrom helper class","will check and update the PR"]}}
out={"stage":"R406_PUBLIC_ORIGINAL_AGENT_TRAJECTORY_INPUT_BOUNDARY","cases":{},"no_experiment":True}
for id,c in cases.items():
 u="https://swe-bench-submissions.s3.amazonaws.com/"+urllib.parse.quote(c["key"])
 req=urllib.request.Request(u,headers={"User-Agent":"TID-R406-verify-one-published-task-trace/1.0"})
 with urllib.request.urlopen(req,timeout=55) as f: b=f.read(800001)
 assert len(b)<=800000 and hashlib.sha256(b).hexdigest()==c["sha256"]
 t=b.decode("utf-8",errors="replace")
 head=t[:25000]
 # Only source-identification features and brief log header; no agent chain-of-thought redistributed.
 rec={"original_public_s3_uri":"s3://swe-bench-submissions/"+c["key"],
  "sha256":c["sha256"],"bytes":len(b),"newlines":t.count("\n"),
  "beginning_500chars":t[:500],
  "first_12_line_prefixes":[line[:130] for line in t.splitlines()[:12]],
  "main_issue_markers":{},
  "historical_discussion_markers":{},
  "user_role_like_markers":{v:t.lower().find(v.lower()) for v in
        ("USER","SYSTEM","ISSUE","Problem Statement","Task","HINTS","metadata")},
  "log_is_complete_prompt_transcript":"NOT_VERIFIED",
  "original_code_story_self_report_no_hints":True}
 for phrase in c["main_phrases"]:
  ix=t.find(phrase)
  rec["main_issue_markers"][phrase]={"found":ix>=0,"first_position":ix,
    "near_start":ix>=0 and ix<25000}
 for phrase in c["history_phrases"]:
  ix=t.find(phrase)
  rec["historical_discussion_markers"][phrase]={"found":ix>=0,"first_position":ix}
 out["cases"][id]=rec
path=pathlib.Path("evidence/R406_CodeStory_two_actual_public_trace_structure.json")
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(out,sort_keys=True,ensure_ascii=False,indent=2)+"\n")
print("TRACE_SIGNATURES",json.dumps({k:{"head":v["beginning_500chars"],"main":v["main_issue_markers"],"hints":v["historical_discussion_markers"]} for k,v in out["cases"].items()},ensure_ascii=False)[:3000])
