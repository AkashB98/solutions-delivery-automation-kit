import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import load_json_file, load_questions
from generator import (generate_docs, generate_ground_truth,
                       generate_library, generate_questionnaire,
                       questionnaire_to_csv, questionnaire_to_json)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "fixtures")


class TestGenerator(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(generate_docs(), generate_docs())
        self.assertEqual(generate_library(), generate_library())
        self.assertEqual(generate_questionnaire(), generate_questionnaire())
        self.assertEqual(generate_ground_truth(), generate_ground_truth())

    def test_counts(self):
        self.assertEqual(len(generate_docs()), 3)
        self.assertEqual(len(generate_library()), 8)
        self.assertEqual(len(generate_questionnaire()), 12)
        kinds = [c["kind"] for c in generate_ground_truth()["cases"]]
        self.assertEqual(kinds.count("library"), 5)
        self.assertEqual(kinds.count("retrieval"), 2)
        self.assertEqual(kinds.count("stale"), 2)
        self.assertEqual(kinds.count("unanswerable"), 3)

    def test_current_versions_carry_two_planted_bumps(self):
        versions = {d["doc_id"]: d["version"] for d in generate_docs()}
        self.assertEqual(versions, {"security-policy": 3,
                                    "deployment-guide": 2,
                                    "compliance-overview": 1})

    def test_truth_covers_every_question_once(self):
        qids = [q["qid"] for q in generate_questionnaire()]
        case_qids = [c["qid"] for c in generate_ground_truth()["cases"]]
        self.assertEqual(sorted(qids), sorted(case_qids))

    def test_bundled_fixtures_match_generator(self):
        self.assertEqual(load_json_file(os.path.join(
            FIXTURES, "source_docs.json")), generate_docs())
        self.assertEqual(load_json_file(os.path.join(
            FIXTURES, "answer_library.json")), generate_library())
        self.assertEqual(load_json_file(os.path.join(
            FIXTURES, "questionnaire.json")), generate_questionnaire())
        self.assertEqual(load_json_file(os.path.join(
            FIXTURES, "ground_truth.json")), generate_ground_truth())

    def test_questionnaire_csv_matches_json(self):
        csv_path = os.path.join(FIXTURES, "questionnaire.csv")
        self.assertEqual(load_questions(csv_path), generate_questionnaire())
        with open(csv_path, encoding="utf-8", newline="") as fh:
            self.assertEqual(questionnaire_to_csv(generate_questionnaire()),
                             fh.read())

    def test_questionnaire_json_round_trip(self):
        text = questionnaire_to_json(generate_questionnaire())
        self.assertEqual(json.loads(text), generate_questionnaire())


if __name__ == "__main__":
    unittest.main()
