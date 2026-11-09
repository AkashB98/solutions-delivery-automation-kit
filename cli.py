"""CLI: generate | library | match | draft | approve | export |
report | check | demo | serve.

SYNTHETIC DATA ONLY — Helios Home is a fictional company and every
dataset handled here is fabricated sample data.

Exit codes:
  check : 0 = pass, 1 = quality breach (match precision / stale
          catch / refusal rate below threshold), 2 = usage / IO /
          data-quality error
  export: 0 = exported, 1 = export refused (unapproved / stale /
          refused draft in the batch — nothing is written),
          2 = usage / IO error
  others: 0 = success, 2 = usage / IO error
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generator import (generate_docs, generate_ground_truth,  # noqa: E402
                       generate_library, generate_questionnaire)
from library import (ExportRefused, approve_drafts, export_answers,  # noqa: E402
                     library_payload, make_drafts)
from matching import match_questionnaire  # noqa: E402
from report import build_report  # noqa: E402
from validation import validate_all  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2
DEFAULT_MIN_PRECISION = 0.99
DEFAULT_MIN_STALE = 1.0
DEFAULT_MIN_REFUSAL = 1.0

_HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_DOCS = os.path.join(_HERE, "fixtures", "source_docs.json")
FIXTURE_LIBRARY = os.path.join(_HERE, "fixtures", "answer_library.json")
FIXTURE_QUESTIONS = os.path.join(_HERE, "fixtures", "questionnaire.json")
FIXTURE_TRUTH = os.path.join(_HERE, "fixtures", "ground_truth.json")


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True)


def load_json_file(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_questions(path: str) -> List[Dict]:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    stripped = text.strip()
    if not stripped:
        return []
    if path.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]
    data = json.loads(stripped)
    if isinstance(data, dict) and "questions" in data:
        return data["questions"]
    return data


def load_drafts(path: str) -> List[Dict]:
    data = load_json_file(path)
    if isinstance(data, dict) and "drafts" in data:
        return data["drafts"]
    return data


def _err(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return EXIT_ERROR


def _load_json_or_none(path: str):
    try:
        return load_json_file(path)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
    except (ValueError, OSError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
    return None


def _load_questions_or_none(path: str):
    try:
        return load_questions(path)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
    except (ValueError, OSError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
    return None


def _load_fixture_set(args):
    docs = _load_json_or_none(args.docs)
    library = _load_json_or_none(args.library)
    if docs is None or library is None:
        return None
    return docs, library


def _load_full(args):
    base = _load_fixture_set(args)
    if base is None:
        return None
    questions = _load_questions_or_none(args.input)
    truth = _load_json_or_none(args.truth)
    if questions is None or truth is None:
        return None
    return base[0], base[1], questions, truth


def _write_out(args, payload, summary: str) -> int:
    text = canonical(payload) + "\n"
    if getattr(args, "out", None):
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(summary)
    else:
        print(text, end="")
    return EXIT_OK


def cmd_generate(args) -> int:
    payload = {"docs": generate_docs(), "library": generate_library(),
               "questionnaire": generate_questionnaire(),
               "ground_truth": generate_ground_truth()}
    return _write_out(args, payload,
                      f"generated {len(payload['library'])} library "
                      f"answers, {len(payload['questionnaire'])} "
                      f"questions -> {args.out}")


def cmd_library(args) -> int:
    base = _load_fixture_set(args)
    if base is None:
        return EXIT_ERROR
    docs, library = base
    payload = library_payload(library, docs)
    return _write_out(args, payload,
                      f"library: {payload['total']} answers, "
                      f"{payload['stale_count']} stale -> {args.out}")


def cmd_match(args) -> int:
    loaded = _load_full(args)
    if loaded is None:
        return EXIT_ERROR
    docs, library, questions, _truth = loaded
    results = match_questionnaire(questions, library, docs)
    payload = {"results": results, "count": len(results)}
    return _write_out(args, payload, f"match: {len(results)} questions "
                                     f"-> {args.out}")


def _drafts_for(args):
    loaded = _load_full(args)
    if loaded is None:
        return None
    docs, library, questions, _truth = loaded
    return make_drafts(match_questionnaire(questions, library, docs))


def cmd_draft(args) -> int:
    drafts = _drafts_for(args)
    if drafts is None:
        return EXIT_ERROR
    payload = {"drafts": drafts, "count": len(drafts)}
    return _write_out(args, payload, f"draft: {len(drafts)} drafts "
                                     f"-> {args.out}")


def cmd_approve(args) -> int:
    try:
        drafts = load_drafts(args.input)
    except FileNotFoundError:
        return _err(f"file not found: {args.input}")
    except (ValueError, OSError) as exc:
        return _err(f"cannot read {args.input}: {exc}")
    qids = args.qid or None
    approved, errors = approve_drafts(drafts, qids)
    payload = {"drafts": approved, "count": len(approved),
               "errors": errors}
    return _write_out(args, payload,
                      f"approve: {sum(1 for d in approved if d['state'] == 'approved')}"
                      f" approved, {len(errors)} refused -> {args.out}")


def cmd_export(args) -> int:
    try:
        drafts = load_drafts(args.input)
    except FileNotFoundError:
        return _err(f"file not found: {args.input}")
    except (ValueError, OSError) as exc:
        return _err(f"cannot read {args.input}: {exc}")
    try:
        payload = export_answers(drafts)
    except ExportRefused as exc:
        # Zero leaks: the refusal goes to stderr and NOTHING is
        # written to --out or stdout.
        print(f"export REFUSED: {exc}", file=sys.stderr)
        return EXIT_FAIL
    return _write_out(args, payload,
                      f"export: {payload['exported_count']} answers "
                      f"-> {args.out}")


def cmd_report(args) -> int:
    loaded = _load_full(args)
    if loaded is None:
        return EXIT_ERROR
    docs, library, questions, truth = loaded
    report = build_report(docs, library, questions, truth)
    return _write_out(args, report, f"report -> {args.out}")


def cmd_check(args) -> int:
    loaded = _load_full(args)
    if loaded is None:
        return EXIT_ERROR
    docs, library, questions, truth = loaded
    issues = validate_all(docs, library, questions)
    if issues:
        for issue in issues[:20]:
            print(f"data-quality: {issue}")
        print(f"check FAIL (data quality): {len(issues)} issue(s)")
        return EXIT_ERROR
    report = build_report(docs, library, questions, truth)
    s = report["scores"]
    r = report["reuse"]
    print(f"questions={r['total_questions']} precision={s['match_precision']} "
          f"stale_catch={s['stale_catch_rate']} refusal={s['refusal_rate']} "
          f"reuse_rate={r['reuse_rate']} hours_saved={r['hours_saved']} "
          f"library_stale={report['library']['stale_count']}")
    breaches = []
    if s["match_precision"] < args.min_precision:
        breaches.append(f"match precision {s['match_precision']} below "
                        f"{args.min_precision}")
    if s["stale_catch_rate"] < args.min_stale_catch:
        breaches.append(f"stale catch rate {s['stale_catch_rate']} below "
                        f"{args.min_stale_catch}")
    if s["refusal_rate"] < args.min_refusal:
        breaches.append(f"refusal rate {s['refusal_rate']} below "
                        f"{args.min_refusal}")
    if breaches:
        for breach in breaches:
            print(f"check FAIL: {breach}")
        return EXIT_FAIL
    print("check PASS")
    return EXIT_OK


def cmd_demo(args) -> int:
    import demo as demo_mod
    try:
        demo_mod.main()
    except AssertionError as exc:
        print(f"demo FAILED: {exc}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


# ------------------------------------------------------------------- serve

class _Handler(BaseHTTPRequestHandler):
    docs: List[Dict] = []
    library: List[Dict] = []
    truth: Optional[Dict] = None

    def _send_json(self, code: int, payload: Any) -> None:
        body = (canonical(payload) + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> Dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw) if raw.strip() else {}
        if not isinstance(body, dict):
            raise ValueError("body must be a JSON object")
        return body

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._send_json(200, {"status": "ok"})
        if self.path == "/report":
            questions = generate_questionnaire()
            return self._send_json(
                200, build_report(self.docs, self.library, questions,
                                  self.truth))
        return self._send_json(404, {"error": "unknown endpoint"})

    def do_POST(self):  # noqa: N802
        try:
            body = self._read_body()
            if self.path == "/draft":
                questions = body.get("questions")
                if questions is None and "question" in body:
                    questions = [{"qid": "Q", "question": body["question"]}]
                if not isinstance(questions, list):
                    raise ValueError("body must contain 'questions'")
                drafts = make_drafts(match_questionnaire(
                    questions, self.library, self.docs))
                return self._send_json(200, {"drafts": drafts,
                                             "count": len(drafts)})
            if self.path == "/export":
                drafts = body.get("drafts")
                if not isinstance(drafts, list):
                    raise ValueError("body must contain 'drafts'")
                try:
                    return self._send_json(200, export_answers(drafts))
                except ExportRefused as exc:
                    return self._send_json(409, {"error": f"export "
                                                  f"refused: {exc}",
                                                 "exported_count": 0})
            return self._send_json(404, {"error": "unknown endpoint"})
        except (ValueError, TypeError, KeyError) as exc:
            return self._send_json(400, {"error": f"bad request: {exc}"})

    def log_message(self, *a: Any) -> None:
        pass


def make_server(port: int) -> HTTPServer:
    _Handler.docs = _load_json_or_none(FIXTURE_DOCS) or generate_docs()
    _Handler.library = _load_json_or_none(FIXTURE_LIBRARY) \
        or generate_library()
    _Handler.truth = _load_json_or_none(FIXTURE_TRUTH) \
        or generate_ground_truth()
    return HTTPServer(("127.0.0.1", port), _Handler)


def cmd_serve(args) -> int:
    server = make_server(args.port)
    print(f"serving on http://127.0.0.1:{args.port}  "
          f"(POST /draft, POST /export, GET /report, GET /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="solutions-delivery-automation-kit",
        description="Solutions-delivery automation: approved-answer "
                    "library matching, stale detection, approval gate "
                    "and export (synthetic sample data only).")
    sub = p.add_subparsers(dest="cmd", required=True)

    def _fixture_args(sp):
        sp.add_argument("--docs", default=FIXTURE_DOCS)
        sp.add_argument("--library", default=FIXTURE_LIBRARY)

    g = sub.add_parser("generate", help="generate the synthetic fixture set")
    g.add_argument("--out", default=None)
    g.set_defaults(func=cmd_generate)

    lb = sub.add_parser("library", help="answer library with stale flags")
    _fixture_args(lb)
    lb.add_argument("--out", default=None)
    lb.set_defaults(func=cmd_library)

    for name, func, helptext in (
            ("match", cmd_match, "match a questionnaire to the library"),
            ("draft", cmd_draft, "match + create drafts (state=draft)")):
        s = sub.add_parser(name, help=helptext)
        _fixture_args(s)
        s.add_argument("--input", default=FIXTURE_QUESTIONS)
        s.add_argument("--truth", default=FIXTURE_TRUTH)
        s.add_argument("--out", default=None)
        s.set_defaults(func=func)

    a = sub.add_parser("approve", help="approve drafts from a draft file")
    a.add_argument("--input", required=True)
    a.add_argument("--qid", action="append", default=None,
                   help="approve only this qid (repeatable); default: all")
    a.add_argument("--out", default=None)
    a.set_defaults(func=cmd_approve)

    e = sub.add_parser("export", help="export approved drafts (all-or-nothing)")
    e.add_argument("--input", required=True)
    e.add_argument("--out", default=None)
    e.set_defaults(func=cmd_export)

    r = sub.add_parser("report", help="combined library/match/reuse report")
    _fixture_args(r)
    r.add_argument("--input", default=FIXTURE_QUESTIONS)
    r.add_argument("--truth", default=FIXTURE_TRUTH)
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_report)

    c = sub.add_parser("check", help="CI gate: exit 0 pass / 1 breach / 2 error")
    _fixture_args(c)
    c.add_argument("--input", default=FIXTURE_QUESTIONS)
    c.add_argument("--truth", default=FIXTURE_TRUTH)
    c.add_argument("--min-precision", type=float, default=DEFAULT_MIN_PRECISION)
    c.add_argument("--min-stale-catch", type=float, default=DEFAULT_MIN_STALE)
    c.add_argument("--min-refusal", type=float, default=DEFAULT_MIN_REFUSAL)
    c.set_defaults(func=cmd_check)

    sub.add_parser("demo", help="run the end-to-end demo").set_defaults(func=cmd_demo)

    s = sub.add_parser("serve", help="localhost JSON API")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
