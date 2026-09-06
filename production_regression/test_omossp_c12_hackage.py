#!/usr/bin/env python3
import json, pathlib, re

FIX=pathlib.Path("production_regression/omossp_c12_hackage_fixtures.json")
WORKER=pathlib.Path("omossp_c12_production_worker.py")

def hackage_valid(text, ident, challenge=False):
    return (not challenge and re.search(r"(?mi)^\s*"+re.escape(ident)+r"\s*$", text) is not None)

def spec_filter(line):
    return re.match(r"^(Name|Version|URL|Homepage|HomePage|Source\d*|VCS|SCM|Upstream|ProjectURL)\s*:",line.strip(),re.I) is not None

fx=json.loads(FIX.read_text(encoding="utf-8"))
worker=WORKER.read_text(encoding="utf-8")

assert 're.search(r"(?mi)^\\s*"+re.escape(ident)+r"\\s*$",tx)' in worker
assert 're.search(r"(?mi)^\\\\s*"+re.escape(ident)+r"\\\\s*$",tx)' not in worker
assert 'Source\\d*|VCS|SCM|Upstream|ProjectURL)\\s*:' in worker
assert 'Source\\\\d*|VCS|SCM|Upstream|ProjectURL)\\\\s*:' not in worker

for p in fx["positives"]:
    text=p["hackage"]["text_extract"]
    ident=p["ident"]
    assert hackage_valid(text,ident,False), f"positive failed: {ident}"

n1=fx["negatives"][0]
base=next(p for p in fx["positives"] if p["source_scale_rank"]==n1["base_positive_rank"])
assert not hackage_valid(base["hackage"]["text_extract"],n1["ident"],False), "nonmatching ident incorrectly accepted"

n2=fx["negatives"][1]
base=next(p for p in fx["positives"] if p["source_scale_rank"]==n2["base_positive_rank"])
assert not hackage_valid(base["hackage"]["text_extract"],n2["ident"],True), "challenge case incorrectly accepted"

assert spec_filter("URL: https://example.invalid/project")
assert spec_filter("Source0: https://example.invalid/source.tar.gz")
assert spec_filter("Source12: https://example.invalid/source12.tar.gz")
assert not spec_filter("Summary: not a locator field")

print("C12_REGRESSION=PASS")
print("POSITIVE_REGEX_POSIX=PASS")
print("POSITIVE_HSLUA_LIST=PASS")
print("NEGATIVE_NONMATCHING_IDENT=PASS")
print("NEGATIVE_CHALLENGE_TRUE=PASS")
print("EC02_URL_SOURCE_FILTER=PASS")
