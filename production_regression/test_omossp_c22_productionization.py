#!/usr/bin/env python3
import hashlib, json, pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
C21=ROOT/"omossp_c21_production_worker.py"
C22=ROOT/"omossp_c22_production_worker.py"
BATCH=ROOT/"production_batches"/"omossp_c18_batch3.json"
CONTRACT=ROOT/"production_contracts"/"omossp_c21_locator_role_qualified_contract_r1.json"
ADDENDUM=ROOT/"production_checkpoints"/"omossp_c21_rank242_corrective_addendum_r1.json"
WF=ROOT/".github"/"workflows"/"omossp-c22-batch3-shard2.yml"

def sha_text(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

c21=C21.read_text(encoding="utf-8")
c22=C22.read_text(encoding="utf-8")
assert sha_text(C21)=="7decd7442e311e75c0d35ea41e1fee112138c44cdf1dd0001ef9c73035b65506"

normalized=c22
reverse=[
  ('UA="OMOSSP-C22-ProductionWorker/1.0"','UA="OMOSSP-C18-ProductionWorker/1.0"'),
  ('OUT=Path("omossp_c22_output")','OUT=Path("omossp_c18_output")'),
  ('if shard != 2:\n    raise SystemExit("C22 authorizes Batch-3 Shard-2 only")',
   'if shard not in (1,2,3,4):\n    raise SystemExit("C18 shard must be 1..4")'),
  ('"protocol":"OMOSSP_PHASE_C22_PRODUCTION_SHARD2_RESULT_R1"',
   '"protocol":"OMOSSP_PHASE_C18_PRODUCTION_SHARD_RESULT_R1"'),
  ('OUT/f"c22_batch3_shard{shard}.json"','OUT/f"c18_batch3_shard{shard}.json"'),
  ('OUT/f"c22_batch3_shard{shard}.sha256"','OUT/f"c18_batch3_shard{shard}.sha256"')
]
for a,b in reverse:
    assert a in normalized, a
    normalized=normalized.replace(a,b,1)
assert normalized==c21, "C22 differs from C21 outside authorized production wiring"

batch=json.loads(BATCH.read_text(encoding="utf-8"))
assert batch["protocol"]=="OMOSSP_PHASE_C18_PRODUCTION_BATCH3_FREEZE_R1"
assert batch["authority_sha256"]=="22d5205d1d89a01d45eb682e1ef672c621c5fd455d07f810ee8cbc04e9ad9bc8"
assert batch["membership_sha256"]=="74c1b9ca2f362ea5cb755b50cadcf3a5820ab59891445bd79fc325da2f28ccdd"
assert batch["selection_freeze_sha256"]=="8ca3a8bb179992c9fbb2ecc00fbba9be7ed2a3857bb4f8f072ba00b9c0f91ebc"
assert len(batch["rows"])==100
assert len(batch["rows"][25:50])==25
assert all(not any("performance" in k.casefold() for k in row) for row in batch["rows"])
canon_rows=json.dumps(batch["rows"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
canon_sel=json.dumps(batch["selection_rule"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
assert hashlib.sha256(canon_rows).hexdigest()==batch["membership_sha256"]
assert hashlib.sha256(canon_sel).hexdigest()==batch["selection_freeze_sha256"]

contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
assert contract["qualified_worker_sha256"]=="7decd7442e311e75c0d35ea41e1fee112138c44cdf1dd0001ef9c73035b65506"
assert contract["exact_runner_sha256"]=="30046d5303ce482e7fb2d8f7f9dd7726b11d648391d7b0e3543fac781ab9c119"
assert contract["batch3_shard2_status"]=="NOT_AUTHORIZED_PENDING_SEPARATE_CONTINUATION_GATE"
assert contract["performance_outcomes_accessed"] is False
assert contract["final_project_entity_id_minted"] is False

add=json.loads(ADDENDUM.read_text(encoding="utf-8"))
assert add["corrective_replay"]["source_scale_rank"]=="242"
assert add["corrective_replay"]["route"]=="AUTO_ACCEPT_P1"
assert add["performance_outcomes_accessed"] is False
assert add["final_project_entity_id_minted"] is False

wf=WF.read_text(encoding="utf-8")
assert "workflow_dispatch:" in wf
assert "pull_request:" not in wf
assert "runs-on: ubuntu-latest" in wf
assert "actions/upload-artifact" not in wf
assert "actions/cache" not in wf
assert "OMOSSP_SHARD: \"2\"" in wf
assert "python omossp_c22_production_worker.py" in wf
assert "production_batches/omossp_c18_batch3.json" in wf

assert "C22 authorizes Batch-3 Shard-2 only" in c22
assert '"search_used":False' in c22
assert '"name_similarity_inference_used":False' in c22
assert '"performance_outcomes_accessed":False' in c22
assert '"final_project_entity_id_minted":False' in c22

print("C22_PRODUCTIONIZATION_PREFLIGHT=PASS")
print("C21_SCIENTIFIC_CORE_BYTE_EQUIVALENT_AFTER_NAMESPACE_NORMALIZATION=TRUE")
print("BATCH3_MEMBERSHIP_SHA=PASS")
print("BATCH3_SELECTION_SHA=PASS")
print("SHARD2_ROWS=25")
print("PRODUCTION_WORKFLOW=MANUAL_ONLY")
print("FREE_ONLY_STATIC_GATE=PASS")
print("PERFORMANCE_SEALED=TRUE")
print("FINAL_PROJECT_ENTITY_ID_MINTED=FALSE")
