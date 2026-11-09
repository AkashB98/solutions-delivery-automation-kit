"""Deterministic matching: approved-answer library first, extractive
retrieval over the source docs only as a fallback.

No LLM, no embeddings library, no network. Matching is TF-IDF cosine
similarity over word tokens — **TF-IDF** — term frequency-inverse
document frequency: a token counts for more when it is frequent in
the query and rare across the corpus, which is what makes a shared
rare word (``subprocessors``) outweigh a shared common one
(``customer``). The same question, worded the same way, always gets
the same score, so every result here is reproducible and pinnable.

Order matters, and it is the whole design:

1. **Library first.** A question that matches a previously approved
   answer is answered from that answer — the same question never
   needs a human twice. If the matched answer's citation is stale
   the result is ``stale_blocked``: stale text is never reused.
2. **Retrieval fallback.** Only when no library entry clears the
   threshold, the question is scored against source-doc sections
   and the best section's text is returned verbatim (extractive —
   assembled, never generated) with its citation.
3. **Refusal.** When neither clears its threshold the result is
   ``refused`` with no answer text at all. Refusing is a feature:
   the alternative is fabricating an answer to a security
   questionnaire.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

LIBRARY_THRESHOLD = 0.45
RETRIEVAL_THRESHOLD = 0.20

# "helios" / "home" are stopwords on purpose: the company name
# appears in questions of every topic, so it carries no topical
# signal — leaving it in let an unanswerable revenue question
# "match" the uptime answer on the strength of the brand alone
# (see README, development loop).
STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for",
    "is", "are", "was", "were", "be", "been", "being", "do", "does",
    "did", "you", "your", "what", "how", "when", "where", "which",
    "who", "often", "long", "many", "much", "have", "has", "can",
    "could", "will", "would", "there", "this", "that", "it", "its",
    "their", "our", "we", "they", "them", "with", "from", "by",
    "at", "as", "into", "any", "all", "each", "helios", "home",
}

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text) -> List[str]:
    if not isinstance(text, str):
        return []
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


def _counts(tokens: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for tok in tokens:
        out[tok] = out.get(tok, 0) + 1
    return out


def _idf(corpus_tokens: List[List[str]]) -> Dict[str, float]:
    n = max(len(corpus_tokens), 1)
    df: Dict[str, int] = {}
    for tokens in corpus_tokens:
        for tok in set(tokens):
            df[tok] = df.get(tok, 0) + 1
    return {tok: math.log((n + 1) / (count + 1)) + 1.0
            for tok, count in df.items()}


def _vector(tokens: List[str], idf: Dict[str, float]) -> Dict[str, float]:
    counts = _counts(tokens)
    total = max(len(tokens), 1)
    return {tok: (count / total) * idf.get(tok, 1.0)
            for tok, count in counts.items()}


def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(value * b.get(tok, 0.0) for tok, value in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return round(dot / (na * nb), 4)


def best_match(question: str, candidates: List[Tuple[str, str]],
               ) -> Tuple[Optional[str], float]:
    """Best (candidate_id, cosine) for ``question`` over candidates.

    ``candidates`` is a list of (id, text); the IDF corpus is the
    candidate texts themselves, so scoring is a pure function of the
    inputs. Ties break to the lowest candidate id, deterministically.
    """
    corpus = [tokenize(text) for _cid, text in candidates]
    idf = _idf(corpus)
    qvec = _vector(tokenize(question), idf)
    best_id, best_score = None, 0.0
    for (cid, _text), tokens in sorted(zip(candidates, corpus),
                                       key=lambda pair: pair[0][0]):
        score = cosine(qvec, _vector(tokens, idf))
        if score > best_score:
            best_id, best_score = cid, score
    return best_id, best_score


def match_question(question: str, library: List[Dict], docs: List[Dict],
                   stale_ids: Optional[set] = None) -> Dict:
    """One question -> one outcome dict (see module docstring)."""
    from library import stale_answer_ids  # local: avoids an import cycle
    if stale_ids is None:
        stale_ids = stale_answer_ids(library, docs)
    lib_candidates = [(entry["answer_id"], entry["question"])
                      for entry in library]
    answer_id, score = best_match(question, lib_candidates)
    if answer_id is not None and score >= LIBRARY_THRESHOLD:
        entry = next(e for e in library if e["answer_id"] == answer_id)
        citation = {"doc_id": entry["source_doc"],
                    "version": entry["source_version"],
                    "section_id": entry["source_section"]}
        if answer_id in stale_ids:
            return {"outcome": "stale_blocked", "answer_id": answer_id,
                    "score": score, "answer": None, "citation": citation}
        return {"outcome": "library", "answer_id": answer_id,
                "score": score, "answer": entry["answer"],
                "citation": citation}
    sections = [(f"{doc['doc_id']}/{sec['section_id']}",
                 sec["heading"] + " " + sec["text"])
                for doc in docs for sec in doc["sections"]]
    section_key, rscore = best_match(question, sections)
    if section_key is not None and rscore >= RETRIEVAL_THRESHOLD:
        doc_id, section_id = section_key.split("/", 1)
        doc = next(d for d in docs if d["doc_id"] == doc_id)
        section = next(s for s in doc["sections"]
                       if s["section_id"] == section_id)
        return {"outcome": "retrieval", "answer_id": None,
                "score": rscore, "answer": section["text"],
                "citation": {"doc_id": doc_id, "version": doc["version"],
                             "section_id": section_id}}
    return {"outcome": "refused", "answer_id": None,
            "score": max(score, rscore) if section_key else score,
            "answer": None, "citation": None}


def match_questionnaire(questions: List[Dict], library: List[Dict],
                        docs: List[Dict]) -> List[Dict]:
    from library import stale_answer_ids
    stale_ids = stale_answer_ids(library, docs)
    results = []
    for q in questions:
        outcome = match_question(q["question"], library, docs, stale_ids)
        results.append({"qid": q["qid"], "question": q["question"],
                        **outcome})
    return results
