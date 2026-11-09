"""Combined report: library health, match quality against the
labelled ground truth, reuse, and a deterministic narrative copied
from the computed numbers. A pure function of its inputs.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from library import library_payload, reuse_metrics  # noqa: E402
from matching import match_questionnaire  # noqa: E402


def score_matches(results: List[Dict], truth: Optional[Dict]) -> Optional[Dict]:
    """Match quality vs the ground truth (None when no truth given).

    * match precision — of the questions the matcher resolved to a
      library answer (fresh or stale-blocked), the share resolved
      to the *right* answer.
    * stale catch — planted stale matches blocked / planted stale.
    * refusal rate — planted unanswerable refused / planted
      unanswerable. Anything below 1.0 means the kit answered a
      question it had no source for.
    * retrieval accuracy — retrieval cases landing on the right
      doc section / planted retrieval cases.
    """
    if truth is None:
        return None
    cases = {c["qid"]: c for c in truth["cases"]}
    by_qid = {r["qid"]: r for r in results}
    predicted_library = [r for r in results
                         if r["outcome"] in ("library", "stale_blocked")]
    correct_library = sum(
        1 for r in predicted_library
        if cases.get(r["qid"], {}).get("answer_id") == r.get("answer_id")
        and cases[r["qid"]]["kind"] in ("library", "stale"))
    precision = round(correct_library / len(predicted_library), 4) \
        if predicted_library else 1.0
    stale_cases = [c for c in truth["cases"] if c["kind"] == "stale"]
    stale_caught = sum(1 for c in stale_cases
                       if by_qid[c["qid"]]["outcome"] == "stale_blocked")
    unanswerable = [c for c in truth["cases"] if c["kind"] == "unanswerable"]
    refused = sum(1 for c in unanswerable
                  if by_qid[c["qid"]]["outcome"] == "refused")
    retrieval = [c for c in truth["cases"] if c["kind"] == "retrieval"]
    retrieval_ok = sum(
        1 for c in retrieval
        if by_qid[c["qid"]]["outcome"] == "retrieval"
        and by_qid[c["qid"]]["citation"]
        and by_qid[c["qid"]]["citation"]["doc_id"] == c["doc_id"]
        and by_qid[c["qid"]]["citation"]["section_id"] == c["section_id"])
    return {
        "match_precision": precision,
        "library_predicted": len(predicted_library),
        "library_correct": correct_library,
        "stale_total": len(stale_cases),
        "stale_caught": stale_caught,
        "stale_catch_rate": round(stale_caught / len(stale_cases), 4)
        if stale_cases else 1.0,
        "unanswerable_total": len(unanswerable),
        "refused_count": refused,
        "refusal_rate": round(refused / len(unanswerable), 4)
        if unanswerable else 1.0,
        "retrieval_total": len(retrieval),
        "retrieval_correct": retrieval_ok,
        "retrieval_accuracy": round(retrieval_ok / len(retrieval), 4)
        if retrieval else 1.0,
    }


def build_report(docs: List[Dict], library: List[Dict],
                 questions: List[Dict],
                 truth: Optional[Dict] = None) -> Dict:
    results = match_questionnaire(questions, library, docs)
    lib = library_payload(library, docs)
    reuse = reuse_metrics(results)
    scores = score_matches(results, truth)
    narrative = (
        f"Library: {lib['total']} approved answers, {lib['stale_count']} "
        f"stale against current source versions "
        f"({', '.join(lib['stale_ids']) or 'none'}). "
        f"Questionnaire: {reuse['total_questions']} questions — "
        f"{reuse['from_library']} answered from the library, "
        f"{reuse['from_retrieval']} by extractive retrieval, "
        f"{reuse['stale_blocked']} blocked as stale, "
        f"{reuse['refused']} refused as unanswerable. "
        f"Reuse rate {reuse['reuse_rate']}; estimated "
        f"{reuse['hours_saved']} human drafting hours avoided."
    )
    if scores is not None:
        narrative += (
            f" Match precision {scores['match_precision']}, stale catch "
            f"rate {scores['stale_catch_rate']}, refusal rate "
            f"{scores['refusal_rate']}, retrieval accuracy "
            f"{scores['retrieval_accuracy']}."
        )
    return {"library": lib, "results": results, "reuse": reuse,
            "scores": scores, "narrative": narrative}
