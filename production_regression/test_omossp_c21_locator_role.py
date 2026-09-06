#!/usr/bin/env python3
import ast, json, pathlib, re

ROOT=pathlib.Path(__file__).resolve().parents[1]
WORKER=ROOT/"omossp_c21_production_worker.py"
FIXTURE=ROOT/"production_regression"/"omossp_c21_locator_role_fixtures.json"

src=WORKER.read_text(encoding="utf-8")
tree=ast.parse(src)
selected=[]
for node in tree.body:
    if isinstance(node,ast.Assign):
        names=[t.id for t in node.targets if isinstance(t,ast.Name)]
        if "IDENTITY_BEARING_SPEC_FIELDS" in names:
            selected.append(node)
    elif isinstance(node,ast.FunctionDef) and node.name=="identity_eligible_origin":
        selected.append(node)
ns={}
exec(compile(ast.Module(body=selected,type_ignores=[]),str(WORKER),"exec"),ns)
eligible=ns["identity_eligible_origin"]
fx=json.loads(FIXTURE.read_text(encoding="utf-8"))

assert fx["performance_outcomes_accessed"] is False
assert fx["final_project_entity_id_minted"] is False
assert src.count("identity_eligible_origin(o)")==3
assert 'any(o.get("origin")=="EC02_SPEC_FIELD" for o in origins)' not in src
assert 'any(o.get("origin")=="EC02_SPEC_FIELD" for o in state["origins"])' not in src

for field in ("URL","Url","url","VCS","vcs"):
    assert eligible({"origin":"EC02_SPEC_FIELD","field":field})
for field in ("Source","Source0","Source1","Source99","Homepage","HomePage","SCM","Upstream","ProjectURL"):
    assert not eligible({"origin":"EC02_SPEC_FIELD","field":field})
assert not eligible({"origin":"EC01_REPO_DOC","field":"URL"})

def candidates(locs):
    return [x["url"] for x in locs if eligible({"origin":"EC02_SPEC_FIELD",**x})]

r242=fx["hg02_rank242"]
assert candidates(r242["locators"])==r242["expected_identity_candidates"]
ctl=fx["synthetic_controls"]
assert candidates(ctl["source_only"])==[]
assert candidates(ctl["same_root_url_source"])==["https://github.com/example/main"]
assert candidates(ctl["conflicting_url_vcs"])==[
    "https://github.com/example/main","https://github.com/example/other"
]
assert candidates(ctl["non_identity_metadata"])==[]

inv=fx["accepted_p1_inventory"]
assert len(inv)==41
for row in inv:
    elig=[x for x in row["locators"] if eligible({"origin":"EC02_SPEC_FIELD",**x})]
    assert any(str(x["field"]).casefold()=="url" for x in elig), row
    basis=row["basis"]
    url=[x["url"] for x in elig if str(x["field"]).casefold()=="url"][0]
    if basis.startswith("Hackage:"):
        assert "/package/"+basis.split(":",1)[1] in url
    elif basis.startswith("MetaCPAN:"):
        assert "/release/"+basis.split(":",1)[1] in url
    elif basis.startswith("PyPI:"):
        assert basis.split(":",1)[1].casefold() in url.casefold()
    else:
        assert url.rstrip("/").casefold()==basis.rstrip("/").casefold(), (row,url)

helper_block=re.search(r"def identity_eligible_origin.*?(?=\ndef )",src,re.S).group(0)
for prohibited in ("similarity","performance","project_entity_id","fuzzy"):
    assert prohibited not in helper_block.casefold()

print("C21_LOCATOR_ROLE_REGRESSION=PASS")
print("ACCEPTED_P1_REPLAY=41_OF_41_STABLE")
print("RANK242_HG02_ROLE_RESOLUTION=PASS")
print("SOURCE_ONLY_AUTO_P1=BLOCKED")
print("URL_VCS_CONFLICT_HG02_SEMANTICS=PRESERVED")
print("PERFORMANCE_SEALED=TRUE")
