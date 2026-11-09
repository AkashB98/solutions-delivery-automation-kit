import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import (generate_docs, generate_library,
                       generate_questionnaire)
from helpers import make_doc, make_entry
from validation import (validate_all, validate_docs, validate_library,
                        validate_questions)


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.docs = generate_docs()
        self.library = generate_library()
        self.questions = generate_questionnaire()

    def test_seeded_fixtures_validate_clean(self):
        self.assertEqual(validate_all(self.docs, self.library,
                                      self.questions), [])

    def test_doc_version_bool_trap(self):
        docs = [make_doc(version=True)]
        self.assertTrue(any("version" in i
                            for i in validate_docs(docs)))

    def test_doc_missing_sections(self):
        doc = make_doc()
        doc["sections"] = []
        self.assertTrue(validate_docs([doc]))

    def test_duplicate_doc_id(self):
        self.assertTrue(validate_docs([make_doc(), make_doc()]))

    def test_library_unknown_doc_and_section(self):
        bad = make_entry(doc_id="nope")
        self.assertTrue(any("unknown source_doc" in i for i in
                            validate_library([bad], self.docs)))
        bad2 = make_entry(doc_id="security-policy", section_id="nope")
        self.assertTrue(any("unknown source_section" in i for i in
                            validate_library([bad2], self.docs)))

    def test_library_status_must_be_approved(self):
        entry = make_entry()
        entry["status"] = "draft"
        docs = [make_doc()]
        self.assertTrue(validate_library([entry], docs))

    def test_library_version_bool_trap(self):
        entry = make_entry(version=True)
        self.assertTrue(validate_library([entry], [make_doc()]))

    def test_duplicate_answer_id(self):
        entries = [make_entry("A1"), make_entry("A1")]
        self.assertTrue(validate_library(entries, [make_doc()]))

    def test_question_defects(self):
        self.assertTrue(validate_questions([{"qid": "Q1",
                                             "question": "  "}]))
        self.assertTrue(validate_questions(
            [{"qid": "Q1", "question": "a?"},
             {"qid": "Q1", "question": "b?"}]))
        self.assertTrue(validate_questions([]))

    def test_planted_defect_in_seeded_library_is_flagged(self):
        library = copy.deepcopy(self.library)
        library[0]["source_section"] = "no-such-section"
        issues = validate_library(library, self.docs)
        self.assertTrue(any("A001" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
