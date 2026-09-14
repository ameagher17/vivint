"""
Data Cloud Ingestion-API + Query + Semantic-Model client for Path 5 observability
seeding. Dependency-free (urllib only; certifi used if present).

Proven end-to-end (Skywave/pronto). Genericised for reuse — nothing org-specific
here; identities come from your generator.

AUTH: client-credentials grant. Create a Connected App with the OAuth scopes
`cdp_ingest_api` + `cdp_query_api` (+ `api`), enable the client-credentials flow with a
run-as user, and put its key/secret in the environment:
    DC_CONSUMER_KEY, DC_CONSUMER_SECRET
    DC_INSTANCE_URL   (your my.salesforce.com — token host)
    DC_LOGIN_URL      (optional; defaults to DC_INSTANCE_URL then login.salesforce.com)
(If your app is wired for JWT instead, swap the first _form_post below for a JWT
assertion grant — the a360→CDP exchange after it is identical. Full auth recipe:
the sibling `sf-datacloud-api-auth` skill.)

HOST SPLIT (the #1 404 cause):
  * Core proxy = <instance>.my.salesforce.com/services/data/v62.0/ssot/...
                 connection / schema / data-stream / mapping / semantic-model CRUD.
  * CDP edge   = <tenant>.c360a.salesforce.com/api/v1|v2/...   ingest jobs + query.
"""
import json, os, ssl, time
import urllib.request, urllib.error, urllib.parse

SSOT = "/services/data/v62.0/ssot"
SEMANTIC_API_VERSION = "v67.0"   # semantic-model endpoints (see read_semantic_model)

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
    try:
        _SSL_CTX.load_default_certs()
    except Exception:
        pass
    if not _SSL_CTX.get_ca_certs():
        _SSL_CTX.check_hostname = False
        _SSL_CTX.verify_mode = ssl.CERT_NONE


def _form_post(url, form):
    data = "&".join("%s=%s" % (k, urllib.parse.quote(str(v), safe="")) for k, v in form.items()).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60, context=_SSL_CTX) as r:
        return json.loads(r.read().decode())


class DC:
    def __init__(self):
        inst = (os.environ.get("DC_INSTANCE_URL") or os.environ.get("DC_LOGIN_URL")
                or "https://login.salesforce.com").rstrip("/")
        core = _form_post(inst + "/services/oauth2/token", {
            "grant_type": "client_credentials",
            "client_id": os.environ["DC_CONSUMER_KEY"],
            "client_secret": os.environ["DC_CONSUMER_SECRET"],
        })
        self.core_token = core["access_token"]
        self.core_url = core["instance_url"].rstrip("/")
        dc = _form_post(self.core_url + "/services/a360/token", {
            "grant_type": "urn:salesforce:grant-type:external:cdp",
            "subject_token": self.core_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        })
        edge = dc["instance_url"]
        self.cdp_url = (edge if edge.startswith("http") else "https://" + edge).rstrip("/")
        self.cdp_token = dc["access_token"]

    # ---- raw HTTP -----------------------------------------------------------
    def _req(self, host, path, method="GET", body=None, ctype="application/json", raw=False):
        base = self.core_url if host == "core" else self.cdp_url
        token = self.core_token if host == "core" else self.cdp_token
        data = None
        headers = {"Authorization": "Bearer " + token}
        if body is not None:
            headers["Content-Type"] = ctype
            data = body if raw else json.dumps(body).encode()
            if raw and isinstance(data, str):
                data = data.encode()
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120, context=_SSL_CTX) as r:
                txt = r.read().decode()
                return r.status, (json.loads(txt) if txt.strip() and txt.lstrip()[:1] in "[{" else txt)
        except urllib.error.HTTPError as e:
            txt = e.read().decode()
            try:
                return e.code, json.loads(txt)
            except Exception:
                return e.code, txt

    def core(self, path, method="GET", body=None):
        return self._req("core", path, method, body)

    def edge(self, path, method="GET", body=None, ctype="application/json", raw=False):
        return self._req("cdp", path, method, body, ctype, raw)

    # ---- Ingestion API: source / schema / stream / mapping (Core proxy) ------
    def find_ingest_connection(self, label):
        st, r = self.core(SSOT + "/connections?connectorType=IngestApi")
        if st == 200 and isinstance(r, dict):
            for c in r.get("connections", r.get("connectionInfoList", [])) or []:
                if label in (c.get("label"), c.get("connectorName"), c.get("name")):
                    return c
        return None

    def create_ingest_connection(self, name, label):
        """Returns (submitted_name, returned_name, id). submitted_name == sourceName
        (use it in ingest jobs); returned_name goes in connectorDetails.name."""
        st, r = self.core(SSOT + "/connections?connectorType=IngestApi", "POST",
                          {"connectorType": "IngestApi", "label": label, "name": name})
        if st not in (200, 201):
            raise RuntimeError("connection create failed %s: %s" % (st, r))
        return name, r.get("name", name), r.get("id")

    def put_schema(self, conn_id, obj_name, fields):
        """fields: list of (name, dataType) in Text|Number|Date|DateTime."""
        body = {"schemas": [{"label": obj_name, "name": obj_name, "schemaType": "IngestApi",
                             "fields": [{"name": n, "label": n, "dataType": dt} for n, dt in fields]}]}
        st, r = self.core(SSOT + "/connections/%s/schema" % conn_id, "PUT", body)
        if st not in (200, 201):
            raise RuntimeError("schema PUT failed %s: %s" % (st, r))
        return r

    def create_stream(self, stream_name, returned_conn_name, obj_name, pk,
                      category="Other", event_time_field=None, retries=4):
        dlo_info = {"label": stream_name, "category": category,
                    "dataspaceInfo": [{"name": "default"}],
                    "dataLakeFieldInputRepresentations": [
                        {"name": pk, "label": pk, "dataType": "Text", "isPrimaryKey": True}]}
        if category == "Engagement" and event_time_field:
            dlo_info["eventDateTimeFieldName"] = event_time_field
        body = {"name": stream_name, "datastreamType": "INGESTAPI",
                "connectorInfo": {"connectorType": "IngestApi",
                                  "connectorDetails": {"name": returned_conn_name, "events": [obj_name]}},
                "dataLakeObjectInfo": dlo_info,
                "refreshConfig": {"refreshMode": "UPSERT"}}
        last = None
        for _ in range(retries):
            st, r = self.core(SSOT + "/data-streams", "POST", body)
            if st in (200, 201):
                return r
            last = (st, r)
            if st == 400 and isinstance(r, list) and "try again" in json.dumps(r):
                time.sleep(8); continue
            break
        raise RuntimeError("stream create failed %s" % (last,))

    def find_stream_dlo(self, base):
        """Match the auto-suffixed stream name '<base>_<event>_<hash>' at the base
        boundary (so 'AiAgentTag' doesn't match 'AiAgentTagDefinition')."""
        st, r = self.core(SSOT + "/data-streams?limit=200")
        if st == 200 and isinstance(r, dict):
            for ds in r.get("dataStreams", []):
                nm = ds.get("name", "")
                if nm == base or nm.startswith(base + "_"):
                    return nm, ds.get("dataLakeObjectInfo", {}).get("name")
        return None, None

    def create_mapping(self, dlo_dev, dmo_dev, pairs):
        body = {"sourceEntityDeveloperName": dlo_dev, "targetEntityDeveloperName": dmo_dev,
                "fieldMapping": [{"sourceFieldDeveloperName": a, "targetFieldDeveloperName": b}
                                 for a, b in pairs]}
        return self.core(SSOT + "/data-model-object-mappings?dataspace=default", "POST", body)

    def delete_stream(self, stream_name):
        return self.core(SSOT + "/data-streams/%s?shouldDeleteDataLakeObject=true"
                         % urllib.parse.quote(stream_name), "DELETE")

    def delete_connection(self, conn_id):
        return self.core(SSOT + "/connections/%s" % conn_id, "DELETE")

    # ---- DMO metadata (verify target field api names in a new org) -----------
    def dmo_metadata(self, dmo):
        return self.core(SSOT + "/metadata?entityType=DataModelObject&entityName=%s" % dmo)

    # ---- Semantic models (READ the rule behind a dashboard tile) -------------
    # SemanticModel isn't in the Metadata API, but these REST endpoints return the
    # calc-field formulas. Use this when a widget reads 0 to find what drives it —
    # see references/reading-the-semantic-model.md.
    def list_semantic_models(self):
        return self.core("/services/data/%s/ssot/semantic/models" % SEMANTIC_API_VERSION)

    def read_semantic_model(self, api_name):
        return self.core("/services/data/%s/ssot/semantic/models/%s"
                         % (SEMANTIC_API_VERSION, api_name))

    # ---- ingest job lifecycle (CDP edge) ------------------------------------
    def ingest_csv(self, obj_name, source_name, csv_bytes, operation="upsert", retries=12):
        job = None
        for _ in range(retries):
            st, r = self.edge("/api/v1/ingest/jobs", "POST",
                              {"object": obj_name, "sourceName": source_name, "operation": operation})
            if st in (200, 201):
                job = r["id"]; break
            if st in (404, 409):
                time.sleep(10); continue
            raise RuntimeError("ingest job create failed %s: %s" % (st, r))
        if not job:
            raise RuntimeError("ingest job create did not settle for %s" % obj_name)
        st, r = self.edge("/api/v1/ingest/jobs/%s/batches" % job, "PUT",
                          csv_bytes, ctype="text/csv", raw=True)
        if st not in (200, 202):
            raise RuntimeError("batch upload failed %s: %s" % (st, r))
        st, r = self.edge("/api/v1/ingest/jobs/%s" % job, "PATCH", {"state": "UploadComplete"})
        if st not in (200, 202):
            raise RuntimeError("job close failed %s: %s" % (st, r))
        return job

    def query(self, sql):
        return self.edge("/api/v2/query", "POST", {"sql": sql})
