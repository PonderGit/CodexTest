from __future__ import annotations
import argparse,gzip,hashlib,json,math,random,re
from pathlib import Path
import pandas as pd
SEED=20260927; USABLE={'OK','OK_CAPPED','OK_FALLBACK','OK_FALLBACK_CAPPED'}
AUTO_RE=re.compile(r"\b(automat(?:e|ed|es|ing|ion|ions|ic|ically|ized|ization|izations)|robotic process automation|RPA|machine learning|artificial intelligence)\b",re.I)
ACCOUNT_RE=re.compile(r"\b(financial reporting|internal control(?:s)?(?: over financial reporting)?|ICFR|journal entr(?:y|ies)|general ledger|ledger system(?:s)?|financial close|close process|consolidation|reconciliation|account reconciliation|procure(?:ment)?|purchase[- ]to[- ]pay|accounts payable|accounts receivable|segregation of duties|ITGC|SOX|financial system(?:s)?|accounting system(?:s)?|financial statements?)\b",re.I)
SPEC_SYS_RE=re.compile(r"\b(ERP|enterprise resource planning|financial system(?:s)?|accounting system(?:s)?|general ledger system(?:s)?|SAP|Oracle|Workday|NetSuite|PeopleSoft)\b",re.I)
CONTROL_RE=re.compile(r"\b(automated control(?:s)?|application control(?:s)?|system[- ]generated|interface control(?:s)?|automated workflow(?:s)?|approval workflow(?:s)?|IT[- ]dependent control(?:s)?)\b",re.I)
CHANGE_RE=re.compile(r"\b(implement(?:ed|ing|ation)?|introduc(?:ed|ing|tion)?|deploy(?:ed|ing|ment)?|put into operation|went live|go live|completed implementation|replac(?:ed|ing|ement)?|configur(?:ed|ing|ation)?|launch(?:ed|ing)?|migrat(?:ed|ing|ion)?|upgrad(?:ed|ing|e)?|roll(?:ed|ing)? out|redesign(?:ed|ing)?|automat(?:e|ed|ing|ion)|transition(?:ed|ing)?|new (?:financial|accounting|ERP|enterprise resource planning|general ledger) system)\b",re.I)
PLAN_RE=re.compile(r"\b(plan(?:ned|ning)?|intend(?:ed|ing)?|expect(?:ed|ing)?|design(?:ing|ed)?|in process of|will implement|implementation underway|implementing)\b",re.I)
FAIL_RE=re.compile(r"\b(ineffective|deficien(?:cy|cies)|material weakness|did not operate effectively|failed|configuration issue)\b",re.I)
GENERIC_SYS_RE=re.compile(r"\b(system(?:s)?|process(?:es)?|workflow(?:s)?)\b",re.I)
ACCOUNTING_SOFTWARE_RE=re.compile(r"\b(accounting software|financial reporting software|lease administration software|financial close software|close management software|reconciliation software|journal entr(?:y|ies) software|general ledger software|tax software|payroll software|accounts payable software|accounts receivable software|procurement software|built[- ]in controls?)\b",re.I)
WORKFLOW_RE=re.compile(r"\b(workflow(?:s)?|electronic approval(?:s)?|approval routing)\b",re.I)
CHALLENGE_TERMS=re.compile(r"\b(digitiz(?:e|ed|ing|ation)|digital(?:ization|ized)?|bot(?:s)?|macro(?:s)?|straight[- ]through processing|technology[- ]enabled|workflow(?:s)?|manual process(?:es)?|manual control(?:s)?|software|application(?:s)?|BlackLine|Workiva|OneStream|Hyperion|Coupa|NetSuite|PeopleSoft|JD Edwards|Microsoft Dynamics|Dynamics 365|Sage)\b",re.I)
CHALL_CHANGE=re.compile(r"\b(implement(?:ed|ing|ation)?|introduc(?:ed|ing|tion)?|deploy(?:ed|ing|ment)?|replac(?:ed|ing|ement)?|migrat(?:ed|ing|ion)?|upgrad(?:ed|ing|e)?|automat(?:e|ed|ing|ion)|redesign(?:ed|ing)?|transition(?:ed|ing)?|new|enhanc(?:ed|ing|ement)?|roll(?:ed|ing)? out)\b",re.I)
def sha(p):
 h=hashlib.sha256();
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def near(s):
 for m in CHANGE_RE.finditer(s):
  w=s[max(0,m.start()-450):min(len(s),m.end()+450)]
  if ACCOUNT_RE.search(w) and GENERIC_SYS_RE.search(w):return True
 return False
def screen(sec,status,form):
 if status not in USABLE:return (False,[])
 s=sec[:40000 if form=='10-K' else 30000]; auto=bool(AUTO_RE.search(s));acct=bool(ACCOUNT_RE.search(s));spec=bool(SPEC_SYS_RE.search(s));ctrl=bool(CONTROL_RE.search(s));change=bool(CHANGE_RE.search(s));plan=bool(PLAN_RE.search(s));fail=bool(FAIL_RE.search(s));prox=near(s);soft=bool(ACCOUNTING_SOFTWARE_RE.search(s));wf=False
 for m in WORKFLOW_RE.finditer(s):
  w=s[max(0,m.start()-500):min(len(s),m.end()+500)]
  if ACCOUNT_RE.search(w) and (CHANGE_RE.search(w) or PLAN_RE.search(w) or CONTROL_RE.search(w)):wf=True;break
 comps=[]
 if auto and acct:comps.append('AUTO+ACCOUNTING')
 if ctrl and acct:comps.append('CONTROL+ACCOUNTING')
 if spec and (change or plan or fail):comps.append('SPECIFIC_SYSTEM_CHANGE')
 if prox:comps.append('SYSTEM_CHANGE_PROXIMITY')
 if soft:comps.append('ACCOUNTING_SOFTWARE_OR_BUILTIN_CONTROL')
 if wf:comps.append('ACCOUNTING_WORKFLOW_CHANGE')
 return bool(comps),comps
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--cache-dir',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args();cache=Path(a.cache_dir);out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True);rows=[]
 for y in range(2019,2026):
  meta=pd.read_csv(cache/f'year_{y}'/f'extraction_{y}.csv',dtype=str); texts={}
  with gzip.open(cache/f'year_{y}'/f'sections_{y}.jsonl.gz','rt',encoding='utf-8') as f:
   for line in f:
    r=json.loads(line);texts[r['accession']]=r['section_text']
  for _,r in meta.iterrows():
   sec=texts[r.accession];hit,comps=screen(sec,r.section_status,r.form);rows.append({'cik':r.cik,'accession':r.accession,'year':y,'form':r.form,'section_status':r.section_status,'section_len':int(r.section_len),'candidate_retrieval_hit':int(hit),'retrieval_rule_components':';'.join(comps)})
 df=pd.DataFrame(rows).sort_values(['year','cik','accession']);df.to_csv(out/'screen_core.csv',index=False);(out/'summary.json').write_text(json.dumps({'rows':len(df),'hits':int(df.candidate_retrieval_hit.sum()),'sha256':sha(out/'screen_core.csv')},indent=2))
if __name__=='__main__':main()
