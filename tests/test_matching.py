import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import (generate_docs, generate_ground_truth,
                       generate_library, generate_questionnaire)
from matching import (LIBRARY_THRESHOLD, best_match, cosine, match_question,
                      match_questionnaire, tokenize)
from report import score_matches


class TestTokenizeCosine(unittest.TestCase):
    def test_tokenize_drops_stopwords_and_brand(self):
        self.assertEqual(tokenize("What is the Helios Home uptime?"),
                         ["uptime"])
        self.assertEqual(tokenize("Data, DATA! data?"),
                         ["data", "data", "data"])

    def test_tokenize_non_string(self):
        self.assertEqual(tokenize(None), [])
        self.assertEqual(tokenize(42), [])

    def test_cosine_identical_and_disjoint(self):
        self.assertEqual(cosine({"a": 1.0}, {"a": 1.0}), 1.0)
        self.assertEqual(cosine({"a": 1.0}, {"b": 1.0}), 0.0)
        self.assertEqual(cosine({}, {"a": 1.0}), 0.0)

    def test_best_match_tie_breaks_to_lowest_id(self):
        cid, score = best_match("alpha beta",
                                [("B", "alpha beta"), ("A", "alpha beta")])
        self.assertEqual((cid, score), ("A", 1.0))

    def test_best_match_no_overlap(self):
        cid, score = best_match("zzz qqq", [("A", "alpha beta")])
        self.assertEqual((cid, score), (None, 0.0))


class TestSeededMatching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = generate_docs()
        cls.library = generate_library()
        cls.results = match_questionnaire(
            generate_questionnaire(), cls.library, cls.docs)
        cls.by_qid = {r["qid"]: r for r in cls.results}

    def test_outcome_partition(self):
        outcomes = {}
        for r in self.results:
            outcomes.setdefault(r["outcome"], []).append(r["qid"])
        self.assertEqual(outcomes, {
            "library": ["Q01", "Q02", "Q03", "Q04", "Q05"],
            "retrieval": ["Q06", "Q07"],
            "stale_blocked": ["Q08", "Q09"],
            "refused": ["Q10", "Q11", "Q12"]})

    def test_exact_questions_score_1(self):
        for qid in ("Q01", "Q08", "Q09"):
            self.assertEqual(self.by_qid[qid]["score"], 1.0)

    def test_library_matches_are_the_right_answers(self):
        expected = {"Q01": "A001", "Q02": "A006", "Q03": "A004",
                    "Q04": "A007", "Q05": "A003", "Q08": "A008",
                    "Q09": "A002"}
        for qid, aid in expected.items():
            self.assertEqual(self.by_qid[qid]["answer_id"], aid)

    def test_stale_matches_carry_no_reusable_answer(self):
        for qid in ("Q08", "Q09"):
            self.assertIsNone(self.by_qid[qid]["answer"])
            self.assertIsNotNone(self.by_qid[qid]["citation"])

    def test_retrieval_is_verbatim_doc_text_with_citation(self):
        sections = {(d["doc_id"], s["section_id"]): s["text"]
                    for d in self.docs for s in d["sections"]}
        for qid, key in (("Q06", ("security-policy", "penetration-testing")),
                         ("Q07", ("security-policy", "patching"))):
            r = self.by_qid[qid]
            self.assertEqual(r["answer"], sections[key])
            self.assertEqual((r["citation"]["doc_id"],
                              r["citation"]["section_id"]), key)
            self.assertEqual(r["citation"]["version"], 3)

    def test_refusals_carry_no_answer_and_no_citation(self):
        for qid in ("Q10", "Q11", "Q12"):
            self.assertIsNone(self.by_qid[qid]["answer"])
            self.assertIsNone(self.by_qid[qid]["citation"])

    def test_scores_pinned(self):
        self.assertEqual(self.by_qid["Q02"]["score"], 0.9762)
        self.assertEqual(self.by_qid["Q06"]["score"], 0.625)
        self.assertEqual(self.by_qid["Q07"]["score"], 0.2819)
        self.assertGreaterEqual(self.by_qid["Q03"]["score"],
                                LIBRARY_THRESHOLD)

    def test_match_precision_and_rates(self):
        scores = score_matches(self.results, generate_ground_truth())
        self.assertEqual(scores["match_precision"], 1.0)
        self.assertEqual(scores["stale_catch_rate"], 1.0)
        self.assertEqual(scores["refusal_rate"], 1.0)
        self.assertEqual(scores["retrieval_accuracy"], 1.0)

    def test_single_question_api(self):
        r = match_question("How is customer data encrypted at rest "
                           "and in transit?", self.library, self.docs)
        self.assertEqual((r["outcome"], r["answer_id"]),
                         ("library", "A001"))
        r = match_question("What colour is the chief executive's car?",
                           self.library, self.docs)
        self.assertEqual(r["outcome"], "refused")


if __name__ == "__main__":
    unittest.main()
