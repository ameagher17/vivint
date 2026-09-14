"""Diagnose the blank Analytics tab: is the semantic layer resolving the numbers,
or is this a Tableau Next front-end/provisioning problem?"""
import os, json
from dc_client import DC, SEMANTIC_API_VERSION

MODEL = "sfm_Agentforce_Analytics_Foundations"
dc = DC()

# 1) Model definition: dataspace + measures/tiles it exposes
st, m = dc.read_semantic_model(MODEL)
print("read_semantic_model:", st)
if isinstance(m, dict):
    print("  keys:", list(m.keys()))
    for k in ("dataspace", "dataSpace", "label", "isLocked", "status"):
        if k in m:
            print("  %s = %r" % (k, m[k]))
    # show measure/calc names if present
    for k in ("measures", "calculatedFields", "metrics", "semanticMetrics", "dimensions"):
        v = m.get(k)
        if isinstance(v, list):
            print("  %s (%d): %s" % (k, len(v),
                  [ (x.get("name") or x.get("apiName") or x.get("developerName")) for x in v ][:15]))

# 2) Attempt a semantic-layer query for one tile (Deflection/Containment)
for path in [
    "/services/data/%s/ssot/semantic/models/%s/query" % (SEMANTIC_API_VERSION, MODEL),
    "/services/data/%s/ssot/analytics/query" % SEMANTIC_API_VERSION,
]:
    body = {"measures": [{"name": "Deflection_Rate"}], "dataspace": "default"}
    st, r = dc.core(path, "POST", body)
    print("\nPOST %s -> %s" % (path, st))
    print("  ", (json.dumps(r)[:600] if not isinstance(r, str) else r[:600]))
