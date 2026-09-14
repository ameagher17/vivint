"""Create the 7 AVA-dashboard calculated measurements (from ava_source 713) into
vivint's editable Service_Agent_Analytics_Extension_965 semantic model via SSOT REST.
Idempotent: skips ones that already exist (checks the model first). Dependency-ordered."""
import json, html, sys
from dc_client import DC

MODEL = "Service_Agent_Analytics_Extension_965"
BASE = "Service_Agent_Analytics_Base_965"
EP = "/services/data/v67.0/ssot/semantic/models/%s/calculated-measurements" % MODEL
DROP = {'id','createdBy','createdDate','lastModifiedBy','lastModifiedDate',
        'baseModelApiName','cacheKey','isQueryable'}
# dependency order: bases before the *_100 wrappers
ORDER = ['Containment_Rate_clc','Contact_Resolution_Rate_clc',
         'Customer_Satisfaction_Score_clc','Customer_Effort_Time_Minutes_clc',
         'Containment_100_clc','Resolution_100_clc','Transfer_100_clc']

dc = DC()
d = json.load(open('/tmp/clc713.json'))
lst = d.get('calculatedMeasurements') or d.get('items') or (d if isinstance(d, list) else [])
by = {(m.get('apiName') or m.get('name')): m for m in lst}

st, model = dc.read_semantic_model(MODEL)
have = {c.get('apiName') for c in (model.get('semanticCalculatedMeasurements') or [])}

for name in ORDER:
    if name in have:
        print("SKIP  %s (exists)" % name); continue
    src = by[name]
    payload = {k: v for k, v in src.items() if k not in DROP}
    payload['expression'] = html.unescape(payload['expression'])
    payload['baseModelApiName'] = BASE
    st, r = dc.core(EP, "POST", payload)
    ok = st in (200, 201)
    print("%s  %s -> %s" % ("OK  " if ok else "FAIL", name, st))
    if not ok:
        msg = r.get('message') if isinstance(r, dict) else r
        print("      ", str(msg)[:300])
