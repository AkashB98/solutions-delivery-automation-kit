"""The answer library: staleness, the approval state machine, and
the export gate.

Staleness is a version comparison, nothing more: an approved answer
cites a source doc and the version it was approved against; when
that doc's current version moves on, the answer is stale until a
human re-approves it against the new text. A stale answer may still
be the best textual match for a question — it is still never reused
and never exported.

The state machine is deliberately minimal:

    draft -> approved -> (exported as part of an export payload)

``draft`` is where every matched / retrieved answer starts (nothing
is born approved). ``approve_drafts`` moves a draft to ``approved``
only when its outcome is ``library`` or ``retrieval`` — refused and
stale-blocked drafts can never be approved. ``export_answers`` is
the gate: it refuses the *whole* batch when any draft is not
approved, is stale, or was refused, and it produces no payload at
all in that case — zero leaks, never a partial export with the bad
rows quietly dropped. The fuller, general-purpose approval engine
this mirrors lives in the author's ``tool-approval-gate`` project;
this one is scoped to questionnaire answers.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# Estimated human drafting time avoided, in hours, per question.
# A library reuse replaces a full draft-and-review cycle (0.5h);
# an extractive retrieval draft still needs shaping (0.25h saved).
LIBRARY_HOURS_SAVED = 0.5
RETRIEVAL_HOURS_SAVED = 0.25

APPROVABLE_OUTCOMES = {"library", "retrieval"}


def docs_by_id(docs: List[Dict]) -> Dict[str, Dict]:
    return {doc["doc_id"]: doc for doc in docs}


def is_stale(entry: Dict, docs: List[Dict]) -> bool:
    doc = docs_by_id(docs).get(entry["source_doc"])
    if doc is None:
        return True
    return entry["source_version"] != doc["version"]


def stale_answer_ids(library: List[Dict], docs: List[Dict]) -> set:
    return {entry["answer_id"] for entry in library
            if is_stale(entry, docs)}


def library_payload(library: List[Dict], docs: List[Dict]) -> Dict:
    stale = stale_answer_ids(library, docs)
    entries = []
    for entry in sorted(library, key=lambda e: e["answer_id"]):
        row = dict(entry)
        row["stale"] = entry["answer_id"] in stale
        entries.append(row)
    return {"entries": entries, "total": len(entries),
            "stale_count": len(stale),
            "stale_ids": sorted(stale),
            "fresh_count": len(entries) - len(stale)}


def make_drafts(match_results: List[Dict]) -> List[Dict]:
    """Match results -> drafts. Every draft starts in state draft."""
    drafts = []
    for result in match_results:
        drafts.append({
            "qid": result["qid"],
            "question": result["question"],
            "outcome": result["outcome"],
            "answer_id": result.get("answer_id"),
            "score": result.get("score"),
            "answer": result.get("answer"),
            "citation": result.get("citation"),
            "state": "draft",
        })
    return drafts


def approve_drafts(drafts: List[Dict], qids=None) -> Tuple[List[Dict], List[str]]:
    """Approve drafts (all, or only ``qids``). Returns (drafts, errors).

    Refused and stale-blocked drafts are never approved; attempting
    one is reported in ``errors`` and the draft stays a draft.
    """
    wanted = None if qids is None else set(qids)
    errors: List[str] = []
    out = []
    for draft in drafts:
        row = dict(draft)
        if wanted is None or row["qid"] in wanted:
            if row["outcome"] in APPROVABLE_OUTCOMES and row.get("answer"):
                row["state"] = "approved"
            elif row["state"] != "approved":
                errors.append(
                    f"{row['qid']}: outcome {row['outcome']} "
                    f"cannot be approved")
        out.append(row)
    return out, errors


class ExportRefused(Exception):
    """Raised when an export batch contains anything unexportable."""


def export_answers(drafts: List[Dict]) -> Dict:
    """The export gate. All-or-nothing: any draft that is not in
    state ``approved`` with an approvable, non-stale outcome refuses
    the entire export and no payload is produced (zero leaks)."""
    blockers = []
    for draft in drafts:
        if draft.get("state") != "approved":
            blockers.append(f"{draft['qid']}: state is "
                            f"{draft.get('state')}, not approved")
        elif draft.get("outcome") not in APPROVABLE_OUTCOMES:
            blockers.append(f"{draft['qid']}: outcome "
                            f"{draft.get('outcome')} is not exportable")
        elif not draft.get("answer"):
            blockers.append(f"{draft['qid']}: no answer text")
    if blockers:
        raise ExportRefused("; ".join(blockers))
    answers = [{"qid": d["qid"], "question": d["question"],
                "answer": d["answer"], "citation": d["citation"],
                "outcome": d["outcome"]} for d in drafts]
    return {"answers": answers, "exported_count": len(answers)}


def exportable_subset(drafts: List[Dict]) -> List[Dict]:
    """The drafts that *could* be exported (approved + approvable).

    Used by the demo / report flow to export one questionnaire's
    answerable, approved subset — the refusal path above stays the
    only way a mixed batch is handled: as a refusal, in full.
    """
    return [d for d in drafts
            if d.get("state") == "approved"
            and d.get("outcome") in APPROVABLE_OUTCOMES
            and d.get("answer")]


def reuse_metrics(match_results: List[Dict]) -> Dict:
    total = len(match_results)
    from_library = sum(1 for r in match_results
                       if r["outcome"] == "library")
    from_retrieval = sum(1 for r in match_results
                         if r["outcome"] == "retrieval")
    stale_blocked = sum(1 for r in match_results
                        if r["outcome"] == "stale_blocked")
    refused = sum(1 for r in match_results if r["outcome"] == "refused")
    hours = round(from_library * LIBRARY_HOURS_SAVED
                  + from_retrieval * RETRIEVAL_HOURS_SAVED, 4)
    return {
        "total_questions": total,
        "from_library": from_library,
        "from_retrieval": from_retrieval,
        "stale_blocked": stale_blocked,
        "refused": refused,
        "answered": from_library + from_retrieval,
        "reuse_rate": round(from_library / total, 4) if total else 0.0,
        "answered_rate": round((from_library + from_retrieval) / total, 4)
        if total else 0.0,
        "hours_saved": hours,
    }
