"""No-network enforcement: with sockets blocked, matching, drafting,
approving, exporting and reporting must all still work. (``serve``
is the only intentional exception — it binds loopback on demand,
and is not used here.)"""

import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Blocker:
    def __init__(self, *a, **k):
        raise RuntimeError("network access blocked in hermetic test")


class TestNoNetwork(unittest.TestCase):
    def setUp(self):
        self._real_socket = socket.socket
        socket.socket = _Blocker
        import urllib.request as urlreq
        self._real_urlopen = urlreq.urlopen
        urlreq.urlopen = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("network access blocked in hermetic test"))

    def tearDown(self):
        socket.socket = self._real_socket
        import urllib.request as urlreq
        urlreq.urlopen = self._real_urlopen

    def test_full_pipeline_offline(self):
        from generator import (generate_docs, generate_ground_truth,
                               generate_library, generate_questionnaire)
        from library import approve_drafts, exportable_subset, make_drafts
        from matching import match_questionnaire
        from report import build_report
        docs, library = generate_docs(), generate_library()
        questions = generate_questionnaire()
        results = match_questionnaire(questions, library, docs)
        approved, _ = approve_drafts(make_drafts(results))
        self.assertEqual(len(exportable_subset(approved)), 7)
        report = build_report(docs, library, questions,
                              generate_ground_truth())
        self.assertEqual(report["scores"]["refusal_rate"], 1.0)

    def test_no_module_opens_sockets_at_import(self):
        for mod in ("generator", "matching", "library", "validation",
                    "report", "cli", "demo"):
            sys.modules.pop(mod, None)
        import cli, demo, generator, library, matching, report  # noqa: F401
        import validation  # noqa: F401
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
