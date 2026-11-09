import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import (EXIT_ERROR, EXIT_FAIL, EXIT_OK,
                 main as cli_main, make_server)
from generator import (generate_docs, generate_library,
                       generate_questionnaire)
from library import (approve_drafts, exportable_subset, make_drafts)
from matching import match_questionnaire
from report import build_report


def _run(argv):
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        code = cli_main(argv)
    return code, out.getvalue()


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="solutions-cli-")
        results = match_questionnaire(generate_questionnaire(),
                                      generate_library(), generate_docs())
        self.drafts = make_drafts(results)
        self.drafts_path = os.path.join(self.tmp, "drafts.json")
        with open(self.drafts_path, "w", encoding="utf-8") as fh:
            json.dump({"drafts": self.drafts}, fh)

    def test_generate_command(self):
        code, text = _run(["generate"])
        payload = json.loads(text)
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(len(payload["library"]), 8)
        self.assertEqual(len(payload["questionnaire"]), 12)

    def test_library_command(self):
        code, text = _run(["library"])
        payload = json.loads(text)
        self.assertEqual((code, payload["stale_count"]), (EXIT_OK, 3))
        self.assertEqual(payload["stale_ids"], ["A002", "A005", "A008"])

    def test_match_command(self):
        code, text = _run(["match"])
        payload = json.loads(text)
        self.assertEqual((code, payload["count"]), (EXIT_OK, 12))

    def test_match_command_csv_input(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        csv_path = os.path.join(root, "fixtures", "questionnaire.csv")
        code, text = _run(["match", "--input", csv_path])
        self.assertEqual((code, json.loads(text)["count"]), (EXIT_OK, 12))

    def test_draft_command(self):
        code, text = _run(["draft"])
        payload = json.loads(text)
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(all(d["state"] == "draft"
                            for d in payload["drafts"]))

    def test_approve_command(self):
        out = os.path.join(self.tmp, "approved.json")
        code, _ = _run(["approve", "--input", self.drafts_path,
                        "--out", out])
        self.assertEqual(code, EXIT_OK)
        with open(out, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(sum(1 for d in payload["drafts"]
                             if d["state"] == "approved"), 7)
        self.assertEqual(len(payload["errors"]), 5)

    def test_export_refused_writes_nothing(self):
        approved, _ = approve_drafts(self.drafts)
        path = os.path.join(self.tmp, "mixed.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"drafts": approved}, fh)
        out = os.path.join(self.tmp, "export.json")
        code, _ = _run(["export", "--input", path, "--out", out])
        self.assertEqual(code, EXIT_FAIL)
        self.assertFalse(os.path.exists(out))

    def test_export_clean_batch(self):
        approved, _ = approve_drafts(self.drafts)
        path = os.path.join(self.tmp, "clean.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"drafts": exportable_subset(approved)}, fh)
        code, text = _run(["export", "--input", path])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(text)["exported_count"], 7)

    def test_report_command(self):
        code, text = _run(["report"])
        report = json.loads(text)
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(report["scores"]["match_precision"], 1.0)
        self.assertEqual(report["reuse"]["reuse_rate"], 0.4167)

    def test_check_exit_codes(self):
        code, _ = _run(["check"])
        self.assertEqual(code, EXIT_OK)
        code, _ = _run(["check", "--min-precision", "1.01"])
        self.assertEqual(code, EXIT_FAIL)
        code, _ = _run(["check", "--input", "/tmp/no-such-q-xyz.json"])
        self.assertEqual(code, EXIT_ERROR)

    def test_missing_input_is_exit_2(self):
        code, _ = _run(["match", "--input", "/tmp/nope-xyz.json"])
        self.assertEqual(code, EXIT_ERROR)
        code, _ = _run(["export", "--input", "/tmp/nope-xyz.json"])
        self.assertEqual(code, EXIT_ERROR)


class TestServe(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _req(self, path, payload=None, method="GET"):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_health(self):
        self.assertEqual(self._req("/health"), (200, {"status": "ok"}))

    def test_post_draft_matches_local(self):
        questions = generate_questionnaire()
        status, body = self._req("/draft", {"questions": questions},
                                 method="POST")
        self.assertEqual(status, 200)
        local = make_drafts(match_questionnaire(
            questions, generate_library(), generate_docs()))
        self.assertEqual(body["drafts"], local)

    def test_get_report_matches_local(self):
        from generator import generate_ground_truth
        status, body = self._req("/report")
        self.assertEqual(status, 200)
        self.assertEqual(body, build_report(
            generate_docs(), generate_library(), generate_questionnaire(),
            generate_ground_truth()))

    def test_post_export_gate(self):
        results = match_questionnaire(generate_questionnaire(),
                                      generate_library(), generate_docs())
        approved, _ = approve_drafts(make_drafts(results))
        status, body = self._req("/export", {"drafts": approved},
                                 method="POST")
        self.assertEqual(status, 409)
        self.assertEqual(body["exported_count"], 0)
        status, body = self._req(
            "/export", {"drafts": exportable_subset(approved)},
            method="POST")
        self.assertEqual(status, 200)
        self.assertEqual(body["exported_count"], 7)

    def test_unknown_endpoint_404(self):
        status, _ = self._req("/nope")
        self.assertEqual(status, 404)

    def test_bad_body_400(self):
        status, body = self._req("/draft", {"wrong": []}, method="POST")
        self.assertEqual(status, 400)
        self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main()
