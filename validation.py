"""Data-quality gate for docs, library entries and questions.

Reports issues, never raises on bad data — a malformed fixture maps
to a clean exit code instead of a crash, the same contract as the
sibling kits. Booleans are rejected where a version integer is
required (in Python ``True`` is an ``int``; the classic quiet trap).
"""

from __future__ import annotations

from typing import Dict, List


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_docs(docs) -> List[str]:
    issues: List[str] = []
    if not isinstance(docs, list) or not docs:
        return ["docs must be a non-empty list"]
    seen = set()
    for doc in docs:
        if not isinstance(doc, dict):
            issues.append("doc must be an object")
            continue
        doc_id = doc.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            issues.append("doc missing doc_id")
            continue
        if doc_id in seen:
            issues.append(f"duplicate doc_id {doc_id}")
        seen.add(doc_id)
        if not _is_int(doc.get("version")) or doc["version"] < 1:
            issues.append(f"{doc_id}: version must be a positive integer")
        sections = doc.get("sections")
        if not isinstance(sections, list) or not sections:
            issues.append(f"{doc_id}: sections must be a non-empty list")
            continue
        sec_ids = set()
        for sec in sections:
            if not isinstance(sec, dict) \
                    or not isinstance(sec.get("section_id"), str) \
                    or not sec.get("section_id", "").strip() \
                    or not isinstance(sec.get("text"), str) \
                    or not sec.get("text", "").strip():
                issues.append(f"{doc_id}: section needs section_id + text")
                continue
            if sec["section_id"] in sec_ids:
                issues.append(f"{doc_id}: duplicate section "
                              f"{sec['section_id']}")
            sec_ids.add(sec["section_id"])
    return issues


def validate_library(library, docs) -> List[str]:
    issues: List[str] = []
    if not isinstance(library, list) or not library:
        return ["library must be a non-empty list"]
    doc_map = {d["doc_id"]: d for d in docs if isinstance(d, dict)}
    seen = set()
    for entry in library:
        if not isinstance(entry, dict):
            issues.append("library entry must be an object")
            continue
        aid = entry.get("answer_id")
        if not isinstance(aid, str) or not aid.strip():
            issues.append("library entry missing answer_id")
            continue
        if aid in seen:
            issues.append(f"duplicate answer_id {aid}")
        seen.add(aid)
        for field in ("question", "answer"):
            if not isinstance(entry.get(field), str) \
                    or not entry[field].strip():
                issues.append(f"{aid}: {field} must be a non-empty string")
        if entry.get("status") != "approved":
            issues.append(f"{aid}: status must be 'approved'")
        if not _is_int(entry.get("source_version")) \
                or entry["source_version"] < 1:
            issues.append(f"{aid}: source_version must be a positive int")
        doc = doc_map.get(entry.get("source_doc"))
        if doc is None:
            issues.append(f"{aid}: unknown source_doc "
                          f"{entry.get('source_doc')}")
        elif entry.get("source_section") not in {
                s["section_id"] for s in doc.get("sections", [])}:
            issues.append(f"{aid}: unknown source_section "
                          f"{entry.get('source_section')}")
    return issues


def validate_questions(questions) -> List[str]:
    issues: List[str] = []
    if not isinstance(questions, list) or not questions:
        return ["questionnaire must be a non-empty list"]
    seen = set()
    for q in questions:
        if not isinstance(q, dict):
            issues.append("question must be an object")
            continue
        qid = q.get("qid")
        if not isinstance(qid, str) or not qid.strip():
            issues.append("question missing qid")
            continue
        if qid in seen:
            issues.append(f"duplicate qid {qid}")
        seen.add(qid)
        if not isinstance(q.get("question"), str) \
                or not q["question"].strip():
            issues.append(f"{qid}: question must be a non-empty string")
    return issues


def validate_all(docs, library, questions) -> List[str]:
    issues = validate_docs(docs)
    if not issues:
        issues += validate_library(library, docs)
    issues += validate_questions(questions)
    return issues
