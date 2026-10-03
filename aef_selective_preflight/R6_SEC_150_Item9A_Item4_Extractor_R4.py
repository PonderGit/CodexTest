import re,json,gzip,html as ihtml,unicodedata,sys,time
from pathlib import Path
from collections import Counter
import pandas as pd
DOCS_ROOT=Path('/mnt/data/aef_primary_docs_all'); OUT=Path('/mnt/data/aef_s3_extract_r4corrected'); OUT.mkdir(exist_ok=True)
SCRIPT_RE=re.compile(r'(?is)<(?:script|style|noscript|ix:header|ix:hidden)\b.*?</(?:script|style|noscript|ix:header|ix:hidden)>')
TAG_RE=re.compile(r'(?s)<[^>]+>')
I9A=re.compile(r'(?i)\bitem\s*(?:no\.?\s*)?9\s*a\b'); I9B=re.compile(r'(?i)\bitem\s*(?:no\.?\s*)?9\s*b\b'); I9C=re.compile(r'(?i)\bitem\s*(?:no\.?\s*)?9\s*c\b'); I10=re.compile(r'(?i)\bitem\s*(?:no\.?\s*)?10\b'); I4=re.compile(r'(?i)\bitem\s*(?:no\.?\s*)?4\b'); CTRL=re.compile(r'(?i)\bcontrols?\s+and\s+procedures\b'); PARTII=re.compile(r'(?i)\bpart\s*ii\b'); PARTIII=re.compile(r'(?i)\bpart\s*iii\b')
S10=[re.compile(x,re.I) for x in [r'evaluation of disclosure controls',r'management.?s annual report on internal control',r'internal control over financial reporting',r'changes in internal control']]
S4=[re.compile(x,re.I) for x in [r'evaluation of disclosure controls',r'changes in internal control',r'internal control over financial reporting']]
CAP={'10-K':80000,'10-Q':50000}

def html_text(path):
    s=Path(path).read_bytes().decode('utf-8','ignore'); s=SCRIPT_RE.sub(' ',s); s=TAG_RE.sub(' ',s); s=ihtml.unescape(s); s=unicodedata.normalize('NFKC',s); return ' '.join(s.split())

def bounded(t,start,ends,cap):
    loc=[]
    for p in ends:
        m=p.search(t,start+1)
        if m: loc.append(m.start())
    natural=min(loc) if loc else None
    hard=min(len(t),start+cap)
    end=min(natural,hard) if natural is not None else hard
    return t[start:end].strip(), bool(natural is None or natural>hard), natural

def qscore(sec,form):
    first=sec[:700]
    head=2 if (re.search(r'(?i)\bitem\s*(?:no\.?\s*)?9\s*a\b.{0,180}\bcontrols?\s+and\s+procedures\b',first) if form=='10-K' else re.search(r'(?i)\bitem\s*(?:no\.?\s*)?4\b.{0,180}\bcontrols?\s+and\s+procedures\b',first)) else 0
    structs=S10 if form=='10-K' else S4
    st=sum(bool(p.search(sec[:15000])) for p in structs)
    length=2 if 250<=len(sec)<=30000 else (1 if 120<=len(sec)<=CAP[form] else 0)
    return (head,st,length,min(len(sec),30000))

def choose(cands,form):
    usable=[c for c in cands if len(c[0])>=120]
    pool=usable or cands
    if not pool:return ('','NO_HEADING')
    sec,capped=max(pool,key=lambda z:qscore(z[0],form))
    if re.search(r'(?i)\bomitted\b',sec[:700]) and len(sec)<1200:return sec,'OMITTED'
    if len(sec)<120:return sec,'SHORT'
    return sec,('OK_CAPPED' if capped else 'OK')

def extract(t,form):
    if form=='10-K':
        c=[]
        for m in I9A.finditer(t):
            if CTRL.search(t,m.end(),min(len(t),m.end()+700)):
                sec,cap,_=bounded(t,m.start(),(I9B,I9C,I10,PARTIII),CAP[form]); c.append((sec,cap))
        sec,st=choose(c,form)
        if st!='NO_HEADING':return sec,st
        f=[]
        for cm in CTRL.finditer(t):
            pre=t[max(0,cm.start()-1200):cm.start()]; ims=list(I9A.finditer(pre))
            if ims:
                start=max(0,cm.start()-1200)+ims[-1].start(); ss,cap,_=bounded(t,start,(I9B,I9C,I10,PARTIII),CAP[form]); f.append((ss,cap))
        sec,st=choose(f,form); return sec,('OK_FALLBACK_CAPPED' if st=='OK_CAPPED' else ('OK_FALLBACK' if st=='OK' else st))
    c=[]
    for m in I4.finditer(t):
        if CTRL.search(t,m.end(),min(len(t),m.end()+700)):
            sec,cap,_=bounded(t,m.start(),(PARTII,),CAP[form]); c.append((sec,cap))
    sec,st=choose(c,form)
    if st!='NO_HEADING':return sec,st
    f=[]
    for cm in CTRL.finditer(t):
        pre=t[max(0,cm.start()-1200):cm.start()]; ims=list(I4.finditer(pre))
        if ims:
            start=max(0,cm.start()-1200)+ims[-1].start(); ss,cap,_=bounded(t,start,(PARTII,),CAP[form]); f.append((ss,cap))
    sec,st=choose(f,form); return sec,('OK_FALLBACK_CAPPED' if st=='OK_CAPPED' else ('OK_FALLBACK' if st=='OK' else st))

def main(y):
    t0=time.time(); d=pd.read_csv(f'/mnt/data/manifest_{y}.csv',dtype=str); rows=[]
    for _,r in d.iterrows():
        tx=html_text(DOCS_ROOT/f'docs_{y}'/r.local_name); sec,st=extract(tx,r.form)
        rows.append({'cik':r.cik,'company_name':r.company_name,'accession':r.accession,'filing_date':r.filing_date,'report_date':r.report_date,'year':y,'form':r.form,'primary_document':r.primary_document,'primary_url':r.primary_url,'local_name':r.local_name,'source_sha256':r.sha256,'section_status':st,'section_len':len(sec),'section_text':sec})
    yd=OUT/f'year_{y}'; yd.mkdir(exist_ok=True)
    pd.DataFrame([{k:v for k,v in r.items() if k!='section_text'} for r in rows]).to_csv(yd/f'extraction_{y}.csv',index=False)
    with gzip.open(yd/f'sections_{y}.jsonl.gz','wt',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    s=Counter(r['section_status'] for r in rows); print(json.dumps({'year':y,'n':len(rows),'status':dict(s),'max_len':max(len(r['section_text']) for r in rows),'seconds':round(time.time()-t0,2)}))
if __name__=='__main__':main(int(sys.argv[1]))
