"""Create the 5 AVA-dashboard metrics into Extension_965 via SSOT REST. Idempotent."""
import json, html
from dc_client import DC

MODEL = "Service_Agent_Analytics_Extension_965"
BASE = "Service_Agent_Analytics_Base_965"
EP = "/services/data/v67.0/ssot/semantic/models/%s/metrics" % MODEL
DROP = {'id','createdBy','createdDate','lastModifiedBy','lastModifiedDate',
        'baseModelApiName','cacheKey','isQueryable'}
NAMES = ['Containment_Rate_mtc','Customer_Satisfaction_Score_mtc','Customer_Effort_Time_mtc',
         'Contact_Resolution_Rate_mtc','Transfer_Rate_mtc']

dc = DC()
d = json.load(open('/tmp/ext713.json'))
by = {m.get('apiName'): m for m in (d.get('semanticMetrics') or [])}

st, model = dc.read_semantic_model(MODEL)
have = {m.get('apiName') for m in (model.get('semanticMetrics') or [])}

for name in NAMES:
    if name in have:
        print("SKIP  %s (exists)" % name); continue
    payload = {k: v for k, v in by[name].items() if k not in DROP}
    payload['baseModelApiName'] = BASE
    st, r = dc.core(EP, "POST", payload)
    ok = st in (200, 201)
    print("%s  %s -> %s" % ("OK  " if ok else "FAIL", name, st))
    if not ok:
        msg = r.get('message') if isinstance(r, dict) else r
        print("      ", str(msg)[:400])
