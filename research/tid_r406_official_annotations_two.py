"""R406 source-only: extract exact two cases from OpenAI 2024 public annotation ZIP.
No model, patch, benchmark or human evaluation is executed.
"""
import urllib.request, io, zipfile, hashlib, json, csv, pathlib
URL="https://cdn.openai.com/introducing-swe-bench-verified/swe-bench-annotation-results.zip"
IDS=("pylint-dev__pylint-4661","matplotlib__matplotlib-26466")
out=pathlib.Path("evidence")
out.mkdir(exist_ok=True)
req=urllib.request.Request(URL,headers={"User-Agent":"TID-R406-two-case-original-annotation-source/1.0"})
with urllib.request.urlopen(req,timeout=65) as f: data=f.read(85000001)
assert len(data)<=85000000,"STOP over bounded transfer"
assert zipfile.is_zipfile(io.BytesIO(data)),"STOP ZIP invalid"
z=zipfile.ZipFile(io.BytesIO(data))
files=z.infolist()
assert len(files)<=1000,"STOP archive unexpectedly large"
meta={"origin":URL,"original_download_bytes":len(data),"original_zip_sha256":hashlib.sha256(data).hexdigest(),
"archive_file_count":len(files),
"archive_files":[{"name":x.filename,"bytes":x.file_size,"crc":x.CRC} for x in files],
"target_ids":list(IDS),"matches":[],"record_total_parsed":0,
"readme_excerpt":{},"source_type":"FIRSTPARTY_PUBLISHED_2024_ANNOTATIONS","no_models_or_tests":True}
def match_row(row, source_name, row_index):
  if not isinstance(row,dict):return
  cols=[k for k,v in row.items() if isinstance(v,str) and any(t in v for t in IDS)]
  if not cols:return
  vals=" ".join(str(row.get(k,"")) for k in ("instance_id","task_id","sample_id","instance","id"))
  ids=[id for id in IDS if id in vals]
  if not ids:
    ids=[id for id in IDS if any(id in str(v) for v in row.values())]
  if not ids:return
  meta["matches"].append({"source":source_name,"row_index":row_index,"ids":ids,"row":row})
for info in files:
  if info.is_dir():continue
  assert info.file_size<35000000,"STOP unexpectedly large member"
  name=info.filename
  lower=name.lower()
  if not lower.endswith((".csv",".json",".jsonl",".txt",".md",".tsv")):continue
  raw=z.read(info)
  decoded=raw.decode("utf-8-sig",errors="replace")
  if lower.endswith((".md",".txt")):
    meta["readme_excerpt"][name]=decoded[:900]
    continue
  if not any(x.encode() in raw for x in IDS):
    continue
  if lower.endswith((".csv",".tsv")):
    reader=csv.DictReader(io.StringIO(decoded),delimiter="," if lower.endswith(".csv") else "\t")
    for i,row in enumerate(reader):
      meta["record_total_parsed"]+=1
      match_row(row,name,i)
  else:
    if lower.endswith(".jsonl"):
      for i,line in enumerate(decoded.splitlines()):
        if not line.strip():continue
        try:r=json.loads(line)
        except json.JSONDecodeError:continue
        meta["record_total_parsed"]+=1
        match_row(r,name,i)
    else:
      x=json.loads(decoded)
      arr=x if isinstance(x,list) else (x.get("rows") if isinstance(x,dict) and isinstance(x.get("rows"),list) else None)
      if arr is not None:
        for i,row in enumerate(arr):
          meta["record_total_parsed"]+=1
          match_row(row,name,i)
      elif isinstance(x,dict):
        for i,(k,row) in enumerate(x.items()):
          if isinstance(row,dict):
            meta["record_total_parsed"]+=1
            match_row({"__dict_key":k,**row},name,i)
assert len(meta["matches"])<=40,"STOP unexpected number of matched original annotations"
p=out/"R406_original_verified_two_task_2024_annotations.json"
p.write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
print("SOURCE_ARCHIVE",len(data),meta["original_zip_sha256"],"FILES",len(files))
print("NAMES",[(x.filename,x.file_size) for x in files][:50])
print("TARGET_ROWS",len(meta["matches"]))
for a in meta["matches"]:
  print("MATCH",a["ids"],a["source"],"INDEX",a["row_index"],"KEYS",list(a["row"].keys()))
