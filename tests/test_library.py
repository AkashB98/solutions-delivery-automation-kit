import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import (generate_docs, generate_library,
                       generate_questionnaire)
from helpers import make_doc, make_draft, make_entry
from library import (ExportRefused, approve_drafts, export_answers,
                     exportable_subset, is_stale, library_payload,
                     make_drafts, reuse_metrics, stale_answer_ids)
from matching import match_questionnaire


class TestStale(unittest.TestCase):
    def test_seeded_stale_set(self):
        self.assertEqual(stale_answer_ids(generate_library(),
                                          generate_docs()),
                         {"A002", "A005", "A008"})

    def test_version_comparison_only(self):
        docs = [make_doc(version=2)]
        self.assertFalse(is_stale(make_entry(version=2), docs))
        self.assertTrue(is_stale(make_entry(version=1), docs))
        self.assertTrue(is_stale(make_entry(version=3), docs))

    def test_unknown_doc_is_stale(self):
        self.assertTrue(is_stale(make_entry(doc_id="nope"),
                                 [make_doc()]))

    def test_library_payload(self):
        payload = library_payload(generate_library(), generate_docs())
        self.assertEqual(payload["total"], 8)
        self.assertEqual(payload["stale_count"], 3)
        self.assertEqual(payload["fresh_count"], 5)
        self.assertEqual(payload["stale_ids"], ["A002", "A005", "A008"])
        flags = {e["answer_id"]: e["stale"] for e in payload["entries"]}
        self.assertTrue(flags["A002"] and flags["A005"] and flags["A008"])
        self.assertFalse(flags["A001"])


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        results = match_questionnaire(generate_questionnaire(),
                                      generate_library(), generate_docs())
        self.drafts = make_drafts(results)

    def test_drafts_start_as_draft(self):
        self.assertTrue(all(d["state"] == "draft" for d in self.drafts))
        self.assertEqual(len(self.drafts), 12)

    def test_approve_all_approves_only_answerable(self):
        approved, errors = approve_drafts(self.drafts)
        self.assertEqual(sum(1 for d in approved
                             if d["state"] == "approved"), 7)
        self.assertEqual(len(errors), 5)

    def test_approve_subset_by_qid(self):
        approved, errors = approve_drafts(self.drafts,
                                          qids=["Q01", "Q10"])
        states = {d["qid"]: d["state"] for d in approved}
        self.assertEqual(states["Q01"], "approved")
        self.assertEqual(states["Q02"], "draft")
        self.assertEqual(len(errors), 1)  # Q10 refused, cannot approve

    def test_approve_does_not_mutate_input(self):
        approve_drafts(self.drafts)
        self.assertTrue(all(d["state"] == "draft" for d in self.drafts))

    def test_refused_and_stale_never_approve(self):
        for outcome in ("refused", "stale_blocked"):
            approved, errors = approve_drafts(
                [make_draft(outcome=outcome, answer=None)])
            self.assertEqual(approved[0]["state"], "draft")
            self.assertEqual(len(errors), 1)


class TestExportGate(unittest.TestCase):
    def test_approved_subset_exports(self):
        drafts = [make_draft("Q1", state="approved"),
                  make_draft("Q2", state="approved")]
        payload = export_answers(drafts)
        self.assertEqual(payload["exported_count"], 2)
        self.assertEqual([a["qid"] for a in payload["answers"]],
                         ["Q1", "Q2"])

    def test_one_unapproved_blocks_the_whole_batch(self):
        drafts = [make_draft("Q1", state="approved"),
                  make_draft("Q2", state="draft")]
        with self.assertRaises(ExportRefused):
            export_answers(drafts)

    def test_stale_blocked_cannot_export_even_if_marked_approved(self):
        drafts = [make_draft("Q1", outcome="stale_blocked",
                             state="approved", answer="old text.")]
        with self.assertRaises(ExportRefused):
            export_answers(drafts)

    def test_refused_cannot_export(self):
        drafts = [make_draft("Q1", outcome="refused", state="approved",
                             answer=None)]
        with self.assertRaises(ExportRefused):
            export_answers(drafts)

    def test_missing_answer_cannot_export(self):
        drafts = [make_draft("Q1", state="approved", answer=None)]
        with self.assertRaises(ExportRefused):
            export_answers(drafts)

    def test_empty_batch_exports_empty(self):
        self.assertEqual(export_answers([])["exported_count"], 0)

    def test_exportable_subset_selects_exactly_the_exportable(self):
        drafts = [make_draft("Q1", state="approved"),
                  make_draft("Q2", state="draft"),
                  make_draft("Q3", outcome="refused", state="approved",
                             answer=None)]
        self.assertEqual([d["qid"] for d in exportable_subset(drafts)],
                         ["Q1"])


class TestReuseMetrics(unittest.TestCase):
    def test_seeded_reuse(self):
        results = match_questionnaire(generate_questionnaire(),
                                      generate_library(), generate_docs())
        m = reuse_metrics(results)
        self.assertEqual(m, {"total_questions": 12, "from_library": 5,
                             "from_retrieval": 2, "stale_blocked": 2,
                             "refused": 3, "answered": 7,
                             "reuse_rate": 0.4167, "answered_rate": 0.5833,
                             "hours_saved": 3.0})

    def test_empty(self):
        m = reuse_metrics([])
        self.assertEqual((m["reuse_rate"], m["hours_saved"]), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
