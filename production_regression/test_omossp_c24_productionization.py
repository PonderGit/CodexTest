#!/usr/bin/env python3
import hashlib, json, pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
C21=ROOT/"omossp_c21_production_worker.py"
C24=ROOT/"omossp_c24_production_worker.py"
BATCH=ROOT/"production_batches"/"omossp_c18_batch3.json"
C23=ROOT/"production_checkpoints"/"omossp_c23_batch3_shard2_checkpoint_r1.json"
C21ADD=ROOT/"production_checkpoints"/"omossp_c21_rank242_corrective_addendum_r1.json"
WF=ROOT/".github"/"workflows"/"omossp-c24-batch3-shard3.yml"

def sha_file(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

c21=C21.read_text(encoding="utf-8")
c24=C24.read_text(encoding="utf-8")
assert sha_file(C21)=="7decd7442e311e75c0d35ea41e1fee112138c44cdf1dd0001ef9c73035b65506"

normalized=c24
reverse=[
  ('UA="OMOSSP-C24-ProductionWorker/1.0"','UA="OMOSSP-C18-ProductionWorker/1.0"'),
  ('OUT=Path("omossp_c24_output")','OUT=Path("omossp_c18_output")'),
  ('if shard != 3:\n    raise SystemExit("C24 authorizes Batch-3 Shard-3 only")',
   'if shard not in (1,2,3,4):\n    raise SystemExit("C18 shard must be 1..4")'),
  ('"protocol":"OMOSSP_PHASE_C24_PRODUCTION_SHARD3_RESULT_R1"',
   '"protocol":"OMOSSP_PHASE_C18_PRODUCTION_SHARD_RESULT_R1"'),
  ('OUT/f"c24_batch3_shard{shard}.json"','OUT/f"c18_batch3_shard{shard}.json"'),
  ('OUT/f"c24_batch3_shard{shard}.sha256"','OUT/f"c18_batch3_shard{shard}.sha256"')
]
for a,b in reverse:
    assert a in normalized, a
    normalized=normalized.replace(a,b,1)
assert normalized==c21, "C24 differs from C21 outside authorized namespace/shard wiring"

batch=json.loads(BATCH.read_text(encoding="utf-8"))
assert batch["protocol"]=="OMOSSP_PHASE_C18_PRODUCTION_BATCH3_FREEZE_R1"
assert batch["authority_sha256"]=="22d5205d1d89a01d45eb682e1ef672c621c5fd455d07f810ee8cbc04e9ad9bc8"
assert batch["membership_sha256"]=="74c1b9ca2f362ea5cb755b50cadcf3a5820ab59891445bd79fc325da2f28ccdd"
assert batch["selection_freeze_sha256"]=="8ca3a8bb179992c9fbb2ecc00fbba9be7ed2a3857bb4f8f072ba00b9c0f91ebc"
assert len(batch["rows"])==100
assert len(batch["rows"][50:75])==25
assert [str(x["source_scale_rank"]) for x in batch["rows"][50:75]]==["285","286","287","288","289","290","291","292","293","294","295","296","297","298","299","300","301","302","303","304","305","306","307","308","309"]
assert all(not any("performance" in k.casefold() for k in row) for row in batch["rows"])
canon_rows=json.dumps(batch["rows"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
canon_sel=json.dumps(batch["selection_rule"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
assert hashlib.sha256(canon_rows).hexdigest()==batch["membership_sha256"]
assert hashlib.sha256(canon_sel).hexdigest()==batch["selection_freeze_sha256"]

c23=json.loads(C23.read_text(encoding="utf-8"))
assert c23["status"]=="CHECKPOINT_COMMITTED__NO_HUMAN_GATE"
assert c23["authority_sha256"]==batch["authority_sha256"]
assert c23["batch3_membership_sha256"]==batch["membership_sha256"]
assert c23["batch3_selection_freeze_sha256"]==batch["selection_freeze_sha256"]
assert c23["exact_runner_r2_sha256"]=="30046d5303ce482e7fb2d8f7f9dd7726b11d648391d7b0e3543fac781ab9c119"
assert c23["batch3_shard2_executed"] is True
assert c23["batch3_shard2_runner_verified"] is True
assert c23["batch3_shard3_authorized"] is False
assert c23["performance_outcomes_accessed"] is False
assert c23["final_project_entity_id_minted"] is False

add=json.loads(C21ADD.read_text(encoding="utf-8"))
assert add["corrective_replay"]["source_scale_rank"]=="242"
assert add["corrective_replay"]["route"]=="AUTO_ACCEPT_P1"
assert add["c21_worker"]["sha256"]=="7decd7442e311e75c0d35ea41e1fee112138c44cdf1dd0001ef9c73035b65506"

wf=WF.read_text(encoding="utf-8")
assert "workflow_dispatch:" in wf
assert "pull_request:" not in wf
assert "runs-on: ubuntu-latest" in wf
assert "actions/upload-artifact" not in wf
assert "actions/cache" not in wf
assert 'OMOSSP_SHARD: "3"' in wf
assert "python omossp_c24_production_worker.py" in wf
assert "production_batches/omossp_c18_batch3.json" in wf

assert "C24 authorizes Batch-3 Shard-3 only" in c24
assert '"search_used":False' in c24
assert '"name_similarity_inference_used":False' in c24
assert '"performance_outcomes_accessed":False' in c24
assert '"final_project_entity_id_minted":False' in c24

print("C24_PRODUCTIONIZATION_PREFLIGHT=PASS")
print("C21_SCIENTIFIC_CORE_BYTE_EQUIVALENT_AFTER_NAMESPACE_NORMALIZATION=TRUE")
print("C23_CHECKPOINT=PASS")
print("EXACT_RUNNER_R2_SHA=PASS")
print("BATCH3_MEMBERSHIP_SHA=PASS")
print("BATCH3_SELECTION_SHA=PASS")
print("SHARD3_ROWS=25")
print("PRODUCTION_WORKFLOW=MANUAL_ONLY")
print("FREE_ONLY_STATIC_GATE=PASS")
print("PERFORMANCE_SEALED=TRUE")
print("FINAL_PROJECT_ENTITY_ID_MINTED=FALSE")
