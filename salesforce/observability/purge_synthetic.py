"""Purge stale synthetic (AVAObs) rows from every STDM+GenAI DMO by primary key.

teardown (delete stream+connection) does NOT clear harmonised DMO rows, so repeated
pushes across changing configs accumulate duplicate + orphaned physical rows
(step ids embed the outcome name, so a retuned session leaves phantom step rows that
re-push never overwrites). This enumerates ALL synthetic ids currently in each DMO and
issues Ingestion-API delete jobs, leaving the 13 real sessions untouched.

  python3 purge_synthetic.py            # dry-run: enumerate + count only
  python3 purge_synthetic.py --execute  # submit delete jobs
"""
import sys
import time
import schema_stdm as S
import schema_genai as G
from dc_client import DC

# One delete job per DMO: the ingest job-create limit is on concurrent job COUNT, not
# rows (a single-PK-column CSV is tiny), so large chunks minimise jobs => no throttling.
CHUNK = 100000
DS_CANDIDATES = ["ssot__DataSourceId__c", "DataSourceId__c", "KQ_DataSourceId__c"]


def main():
    execute = "--execute" in sys.argv
    dc = DC()
    print("[dc] core=%s cdp=%s  mode=%s" % (dc.core_url, dc.cdp_url, "EXECUTE" if execute else "dry-run"))

    for o in S.OBJECTS + G.OBJECTS:
        dmo = o["dmo"]
        pk_col = o["pk"]                      # ingest-schema PK column (delete CSV header)
        id_field = dict(o["map"])[pk_col]     # DMO field the PK maps to (ssot__Id__c / Id__c)
        base = (S.STREAM_BASE if o in S.OBJECTS else G.STREAM_BASE)[o["object"]]

        # discover the DataSourceId system field for this DMO
        ds_field = None
        for cand in DS_CANDIDATES:
            st, r = dc.query("SELECT COUNT(*) FROM %s WHERE %s LIKE 'AVAObs%%'" % (dmo, cand))
            if st == 200:
                ds_field = cand
                break
        if not ds_field:
            print("  %-34s SKIP: no DataSourceId field found" % o["object"])
            continue

        st, r = dc.query("SELECT DISTINCT %s FROM %s WHERE %s LIKE 'AVAObs%%'" % (id_field, dmo, ds_field))
        if st != 200:
            print("  %-34s ENUM FAIL %s %s" % (o["object"], st, str(r)[:120]))
            continue
        ids = [row[0] for row in r.get("data", []) if row and row[0] is not None]
        print("  %-34s syn ids=%-6d (id=%s ds=%s)" % (o["object"], len(ids), id_field, ds_field))
        if not ids or not execute:
            continue

        for i in range(0, len(ids), CHUNK):
            chunk = ids[i:i + CHUNK]
            csv = (pk_col + "\n" + "\n".join(str(x) for x in chunk) + "\n").encode()
            try:
                job = dc.ingest_csv(o["object"], base, csv, operation="delete")
                print("      delete job %s  rows=%d" % (job, len(chunk)))
            except Exception as e:   # job-create throttle: skip, a re-run picks up remainder
                print("      THROTTLED (%s) — rerun to finish %s" % (str(e)[:60], o["object"]))
            time.sleep(8)   # let open jobs drain before creating the next

    print("done. %s" % ("delete jobs submitted — rows clear in ~1-4 min." if execute else "dry-run only."))


if __name__ == "__main__":
    main()
