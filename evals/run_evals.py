"""Golden evals for solutions-delivery-automation-kit.

SYNTHETIC DATA ONLY (fictional Helios Home). Every eval is
deterministic: run_evals.py writes eval_report.json and the file
must be byte-identical across runs. No timestamps, ports, or temp
paths enter the report — only names, booleans, pinned counts and
values.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import (EXIT_ERROR, EXIT_FAIL, EXIT_OK, load_json_file,  # noqa: E402
                 load_questions, main as cli_main, make_server)
from generator import (generate_docs, generate_ground_truth,  # noqa: E402
                       generate_library, generate_questionnaire,
                       library_to_json, questionnaire_to_json)
from library import (ExportRefused, approve_drafts, export_answers,  # noqa: E402
                     exportable_subset, library_payload, make_drafts,
                     stale_answer_ids)
from matching import match_questionnaire  # noqa: E402
from report import build_report  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(ROOT, "fixtures")
RESULTS = []


def check(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def _run_cli(argv):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return cli_main(argv)


def main():
    print("== golden evals: solutions-delivery-automation-kit ==")
    docs = generate_docs()
    library = generate_library()
    questions = generate_questionnaire()
    truth = generate_ground_truth()
    results = match_questionnaire(questions, library, docs)
    by_qid = {r["qid"]: r for r in results}
    report = build_report(docs, library, questions, truth)
    scores = report["scores"]

    # E1: generator determinism (bytes pinned).
    q_text = questionnaire_to_json(generate_questionnaire())
    lib_text = library_to_json(generate_library())
    q_md5 = hashlib.md5(q_text.encode()).hexdigest()
    lib_md5 = hashlib.md5(lib_text.encode()).hexdigest()
    check("E1 generator determinism (12 questions, 8 library answers)",
          q_text == questionnaire_to_json(generate_questionnaire())
          and q_md5 == "9f2e56872d6fc249fbf6640d4bbc89dd"
          and lib_md5 == "a11f775a523362cff2b97948b6e3fb61",
          f"questionnaire_md5={q_md5} library_md5={lib_md5}")

    # E2: library staleness pinned — the two planted doc bumps
    # (security-policy v2->v3, deployment-guide v1->v2) stale
    # exactly A002, A005, A008 and nothing else.
    payload = library_payload(library, docs)
    check("E2 library stale pinned (3 of 8: A002, A005, A008)",
          payload["stale_ids"] == ["A002", "A005", "A008"]
          and stale_answer_ids(library, docs) == {"A002", "A005", "A008"}
          and payload["fresh_count"] == 5,
          f"stale={payload['stale_ids']}")

    # E3 (headline 1): match precision — every question the matcher
    # resolves to a library answer resolves to the RIGHT answer.
    check("E3 match precision pinned (1.0, 7/7)",
          scores["match_precision"] == 1.0
          and scores["library_predicted"] == 7
          and scores["library_correct"] == 7,
          f"precision={scores['match_precision']}")

    # E4 (headline 2): stale catch is total — both questionnaire
    # questions whose best match is stale are blocked, and blocked
    # results carry no reusable answer text.
    check("E4 stale catch pinned (2/2 blocked, no text leaked)",
          scores["stale_catch_rate"] == 1.0
          and scores["stale_caught"] == 2
          and all(by_qid[q]["answer"] is None
                  for q in ("Q08", "Q09")),
          f"stale_catch={scores['stale_catch_rate']}")

    # E5 (headline 3): refusal rate on planted unanswerable = 1.0,
    # and a refusal is a refusal — no answer, no citation.
    check("E5 refusal pinned (3/3 unanswerable refused, no fabrication)",
          scores["refusal_rate"] == 1.0 and scores["refused_count"] == 3
          and all(by_qid[q]["answer"] is None
                  and by_qid[q]["citation"] is None
                  for q in ("Q10", "Q11", "Q12")),
          f"refusal={scores['refusal_rate']}")

    # E6: retrieval fallback lands on the right sections, verbatim.
    sections = {(d["doc_id"], s["section_id"]): s["text"]
                for d in docs for s in d["sections"]}
    check("E6 retrieval accuracy pinned (2/2, verbatim + cited)",
          scores["retrieval_accuracy"] == 1.0
          and by_qid["Q06"]["answer"]
          == sections[("security-policy", "penetration-testing")]
          and by_qid["Q07"]["answer"]
          == sections[("security-policy", "patching")],
          f"retrieval={scores['retrieval_accuracy']}")

    # E7: reuse pinned — 5 of 12 from the library, 3.0 hours saved.
    reuse = report["reuse"]
    check("E7 reuse pinned (rate 0.4167, 3.0 hours avoided)",
          reuse["reuse_rate"] == 0.4167 and reuse["hours_saved"] == 3.0
          and reuse["from_library"] == 5 and reuse["from_retrieval"] == 2
          and reuse["answered"] == 7,
          f"reuse_rate={reuse['reuse_rate']} hours={reuse['hours_saved']}")

    # E8 (headline 4): the export gate — a mixed batch and an
    # unapproved batch are both refused whole; the CLI refusal
    # writes no file at all (zero leaks); the clean subset exports.
    drafts = make_drafts(results)
    approved, _errors = approve_drafts(drafts)
    mixed_refused = unapproved_refused = False
    try:
        export_answers(approved)
    except ExportRefused:
        mixed_refused = True
    try:
        export_answers([dict(d, state="draft")
                        for d in exportable_subset(approved)])
    except ExportRefused:
        unapproved_refused = True
    tmp = tempfile.mkdtemp(prefix="solutions-evals-")
    mixed_path = os.path.join(tmp, "mixed.json")
    with open(mixed_path, "w", encoding="utf-8") as fh:
        json.dump({"drafts": approved}, fh)
    out_path = os.path.join(tmp, "export.json")
    cli_code = _run_cli(["export", "--input", mixed_path,
                         "--out", out_path])
    clean = export_answers(exportable_subset(approved))
    check("E8 export gate pinned (mixed + unapproved refused, 0 leaks)",
          mixed_refused and unapproved_refused
          and cli_code == EXIT_FAIL and not os.path.exists(out_path)
          and clean["exported_count"] == 7,
          f"cli_refusal_code={cli_code} file_written="
          f"{os.path.exists(out_path)}")

    # E9: state machine — approval succeeds for exactly the 7
    # answerable drafts and is refused for the 5 blocked/refused.
    check("E9 approval state machine pinned (7 approved, 5 refused)",
          sum(1 for d in approved if d["state"] == "approved") == 7
          and len(_errors) == 5
          and all(d["state"] == "draft" for d in approved
                  if d["qid"] in ("Q08", "Q09", "Q10", "Q11", "Q12")))

    # E10: CLI check exit codes 0 / 1 / 2.
    codes = (_run_cli(["check"]),
             _run_cli(["check", "--min-precision", "1.01"]),
             _run_cli(["check", "--input", "/tmp/no-such-q-xyz.json"]))
    check("E10 CLI check exit codes 0/1/2",
          codes == (EXIT_OK, EXIT_FAIL, EXIT_ERROR), f"codes={codes}")

    # E11: serve round-trip matches local computation, and the
    # served export gate refuses the mixed batch with a 409.
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",
                                    timeout=10) as resp:
            health = json.loads(resp.read())

        def _post(path, payload):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read())

        s_draft, served_drafts = _post("/draft", {"questions": questions})
        s_mixed, mixed_body = _post("/export", {"drafts": approved})
        s_clean, clean_body = _post(
            "/export", {"drafts": exportable_subset(approved)})
        serve_ok = health == {"status": "ok"} and s_draft == 200 \
            and served_drafts["drafts"] == drafts \
            and s_mixed == 409 and mixed_body["exported_count"] == 0 \
            and s_clean == 200 and clean_body == clean
    finally:
        server.shutdown()
        server.server_close()
    check("E11 serve round-trip matches local draft + export gate",
          serve_ok)

    # E12: bundled fixtures pinned + report determinism.
    fixture_docs = load_json_file(os.path.join(FIXTURES, "source_docs.json"))
    fixture_lib = load_json_file(os.path.join(FIXTURES, "answer_library.json"))
    fixture_q = load_questions(os.path.join(FIXTURES, "questionnaire.json"))
    fixture_q_csv = load_questions(os.path.join(FIXTURES,
                                                "questionnaire.csv"))
    fixture_truth = load_json_file(os.path.join(FIXTURES,
                                                "ground_truth.json"))
    r1 = json.dumps(report, sort_keys=True)
    r2 = json.dumps(build_report(docs, library, questions, truth),
                    sort_keys=True)
    check("E12 fixtures pinned + report determinism",
          fixture_docs == docs and fixture_lib == library
          and fixture_q == questions and fixture_q_csv == questions
          and fixture_truth == truth and r1 == r2,
          f"report_md5={hashlib.md5(r1.encode()).hexdigest()}")

    passed = sum(1 for r in RESULTS if r["passed"])
    total_count = len(RESULTS)
    summary_doc = {"passed": passed, "total": total_count,
                   "all_passed": passed == total_count, "evals": RESULTS}
    with open(os.path.join(HERE, "eval_report.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(summary_doc, sort_keys=True) + "\n")
    print(f"\n{passed}/{total_count} evals passed -> evals/eval_report.json")
    return 0 if passed == total_count else 1


if __name__ == "__main__":
    sys.exit(main())
