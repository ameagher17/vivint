"""Convert the Customer Effort tile to minutes.

The calc `Customer_Effort_Time_Minutes_clc` is named "Minutes" but returns SECONDS
(DATEDIFF('second', ...)) and is labelled "(seconds)". This makes it actually return
minutes (÷60.0, float to avoid integer truncation) and relabels calc + metric to "(min.)".
Idempotent: skips if already converted.
"""
import json, html, sys
from dc_client import DC

MODEL = "Service_Agent_Analytics_Extension_965"
BASE = "Service_Agent_Analytics_Base_965"
CALC = "Customer_Effort_Time_Minutes_clc"
MTC = "Customer_Effort_Time_mtc"
CALC_EP = "/services/data/v67.0/ssot/semantic/models/%s/calculated-measurements" % MODEL
MTC_EP = "/services/data/v67.0/ssot/semantic/models/%s/metrics" % MODEL
DROP = {'id','createdBy','createdDate','lastModifiedBy','lastModifiedDate',
        'baseModelApiName','cacheKey','isQueryable'}
NEW_LABEL = "Customer Effort Time (min.)"

dc = DC()
st, m = dc.read_semantic_model(MODEL)
calcs = {c.get('apiName'): c for c in (m.get('semanticCalculatedMeasurements') or [])}
mtcs = {c.get('apiName'): c for c in (m.get('semanticMetrics') or [])}

def update(ep, apiName, payload):
    """Try PATCH then PUT then DELETE+POST on the sub-resource."""
    for method in ("PATCH", "PUT"):
        st, r = dc.core(ep + "/" + apiName, method, payload)
        if st in (200, 201):
            return method, st, r
    # fallback: delete + recreate
    dst, dr = dc.core(ep + "/" + apiName, "DELETE")
    st, r = dc.core(ep, "POST", payload)
    return "DELETE+POST(del=%s)" % dst, st, r

# ---- calc ----
c = calcs[CALC]
expr = html.unescape(c.get('expression', ''))
if "/ 60.0" in expr or "/60.0" in expr:
    print("SKIP calc (already minutes)")
else:
    payload = {k: v for k, v in c.items() if k not in DROP}
    payload['expression'] = expr.rstrip() + "\n/ 60.0"
    payload['label'] = NEW_LABEL
    payload['baseModelApiName'] = BASE
    method, st, r = update(CALC_EP, CALC, payload)
    print("CALC  %s -> %s (%s)" % (CALC, st, method))
    if st not in (200, 201):
        print("   ", str(r.get('message') if isinstance(r, dict) else r)[:400])

# ---- metric label ----
mt = mtcs[MTC]
if mt.get('label') == NEW_LABEL:
    print("SKIP metric (already relabelled)")
else:
    payload = {k: v for k, v in mt.items() if k not in DROP}
    payload['label'] = NEW_LABEL
    payload['baseModelApiName'] = BASE
    method, st, r = update(MTC_EP, MTC, payload)
    print("MTC   %s -> %s (%s)" % (MTC, st, method))
    if st not in (200, 201):
        print("   ", str(r.get('message') if isinstance(r, dict) else r)[:400])
