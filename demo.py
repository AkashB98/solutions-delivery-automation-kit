"""End-to-end demo: library -> stale flags -> match questionnaire
-> drafts -> approve -> export gate -> report -> check -> serve.

SYNTHETIC DATA ONLY (fictional Helios Home). Runs fully offline;
the serve round-trip is loopback-only on an ephemeral port.
Every stage asserts.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import EXIT_FAIL, EXIT_OK, main as cli_main, make_server  # noqa: E402
from generator import (generate_docs, generate_ground_truth,  # noqa: E402
                       generate_library, generate_questionnaire)
from library import (ExportRefused, approve_drafts, export_answers,  # noqa: E402
                     exportable_subset, library_payload, make_drafts)
from matching import match_questionnaire  # noqa: E402
from report import build_report  # noqa: E402


def _request(port: int, path: str, payload=None, method: str = "GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def main() -> None:
    docs = generate_docs()
    library = generate_library()
    questions = generate_questionnaire()
    truth = generate_ground_truth()

    print("== 1. answer library: 8 approved answers, version citations ==")
    payload = library_payload(library, docs)
    assert payload["total"] == 8 and payload["stale_count"] == 3, payload
    assert payload["stale_ids"] == ["A002", "A005", "A008"]
    print("   stale after the planted doc bumps (security-policy "
          "v2->v3, deployment-guide v1->v2): A002, A005, A008")

    print("\n== 2. match the 12-question questionnaire, library first ==")
    results = match_questionnaire(questions, library, docs)
    by_outcome = {}
    for r in results:
        by_outcome.setdefault(r["outcome"], []).append(r["qid"])
        print(f"   {r['qid']} -> {r['outcome']} "
              f"({r.get('answer_id') or (r.get('citation') or {}).get('section_id') or '-'}, "
              f"score={r['score']})")
    assert by_outcome == {"library": ["Q01", "Q02", "Q03", "Q04", "Q05"],
                          "retrieval": ["Q06", "Q07"],
                          "stale_blocked": ["Q08", "Q09"],
                          "refused": ["Q10", "Q11", "Q12"]}, by_outcome
    refused = [r for r in results if r["outcome"] == "refused"]
    assert all(r["answer"] is None for r in refused), \
        "a refusal must carry no answer text — no fabrication"

    print("\n== 3. drafts -> approve: refused/stale can never approve ==")
    drafts = make_drafts(results)
    assert all(d["state"] == "draft" for d in drafts)
    approved, errors = approve_drafts(drafts)
    assert len(errors) == 5, errors  # 2 stale-blocked + 3 refused
    states = {d["qid"]: d["state"] for d in approved}
    assert sum(1 for s in states.values() if s == "approved") == 7
    print(f"   7 approved; approval refused for: "
          f"{', '.join(e.split(':')[0] for e in errors)}")

    print("\n== 4. export gate: mixed batch refused whole, zero leaks ==")
    try:
        export_answers(approved)
        raise SystemExit("export of a mixed batch must be refused")
    except ExportRefused as exc:
        print(f"   mixed batch REFUSED ({exc})")
    subset = exportable_subset(approved)
    exported = export_answers(subset)
    assert exported["exported_count"] == 7
    unapproved = [dict(d, state="draft") for d in subset]
    try:
        export_answers(unapproved)
        raise SystemExit("export of unapproved drafts must be refused")
    except ExportRefused:
        print("   unapproved batch REFUSED; approved subset exported 7/7")

    print("\n== 5. report + reuse ==")
    report = build_report(docs, library, questions, truth)
    assert report["scores"]["match_precision"] == 1.0
    assert report["scores"]["stale_catch_rate"] == 1.0
    assert report["scores"]["refusal_rate"] == 1.0
    assert report["reuse"]["reuse_rate"] == 0.4167
    assert report["reuse"]["hours_saved"] == 3.0
    print("   " + report["narrative"])

    print("\n== 6. CLI check gate + CLI draft/approve/export flow ==")
    tmp = tempfile.mkdtemp(prefix="solutions-demo-")
    code_ok = cli_main(["check"])
    drafts_path = os.path.join(tmp, "drafts.json")
    assert cli_main(["draft", "--out", drafts_path]) == EXIT_OK
    approved_path = os.path.join(tmp, "approved.json")
    assert cli_main(["approve", "--input", drafts_path,
                     "--out", approved_path]) == EXIT_OK
    export_path = os.path.join(tmp, "export.json")
    code_refused = cli_main(["export", "--input", approved_path,
                             "--out", export_path])
    assert code_refused == EXIT_FAIL and not os.path.exists(export_path), \
        "a refused export must write nothing — zero leaks"
    with open(approved_path, encoding="utf-8") as fh:
        approved_doc = json.load(fh)
    clean = {"drafts": exportable_subset(approved_doc["drafts"])}
    clean_path = os.path.join(tmp, "clean.json")
    with open(clean_path, "w", encoding="utf-8") as fh:
        json.dump(clean, fh)
    assert cli_main(["export", "--input", clean_path,
                     "--out", export_path]) == EXIT_OK
    print(f"   check={code_ok}, mixed export={code_refused} (no file "
          f"written), clean export=0")

    print("\n== 7. live localhost serve round-trip ==")
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, health = _request(port, "/health")
        assert status == 200 and health == {"status": "ok"}
        status, served = _request(port, "/draft",
                                  payload={"questions": questions},
                                  method="POST")
        assert status == 200 and served["drafts"] == drafts
        status, served_report = _request(port, "/report")
        assert status == 200 and served_report == report
        status, refused_export = _request(
            port, "/export", payload={"drafts": approved}, method="POST")
        assert status == 409 and refused_export["exported_count"] == 0
        status, ok_export = _request(
            port, "/export", payload={"drafts": subset}, method="POST")
        assert status == 200 and ok_export == exported
        print("   POST /draft, GET /report match local; POST /export "
              "409 on mixed batch, 200 on the approved subset")
    finally:
        server.shutdown()
        server.server_close()

    print("\nDemo OK: library, stale, match, draft, approve, export, "
          "report, check and serve verified.")


if __name__ == "__main__":
    main()
