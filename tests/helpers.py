"""Shared builders for the test suite (not a test module)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_doc(doc_id="doc-x", version=1, sections=None):
    return {"doc_id": doc_id, "title": "Doc X", "version": version,
            "sections": sections or [
                {"section_id": "s1", "heading": "S1",
                 "text": "alpha beta gamma"}]}


def make_entry(answer_id="AX", version=1, doc_id="doc-x", section_id="s1",
               question="alpha beta?", answer="alpha beta gamma."):
    return {"answer_id": answer_id, "question": question,
            "answer": answer, "source_doc": doc_id,
            "source_version": version, "source_section": section_id,
            "status": "approved"}


def make_draft(qid="Q1", outcome="library", state="draft", answer="text."):
    return {"qid": qid, "question": "q?", "outcome": outcome,
            "answer_id": "A001" if outcome == "library" else None,
            "score": 1.0, "answer": answer,
            "citation": {"doc_id": "security-policy", "version": 3,
                         "section_id": "encryption"},
            "state": state}
