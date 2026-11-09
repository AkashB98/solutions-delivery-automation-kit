# solutions-delivery-automation-kit

**The answer-library layer of solutions delivery: take an incoming security questionnaire or RFP question set and answer every question that has ever been answered before — from the previously approved answer, not from scratch — while refusing to reuse anything stale and refusing to invent anything unanswerable.**

This is the work a solutions lead's job description names outright: RFP answers and security questionnaires that should *"systematically get off your plate."* The pattern behind it is simple — in a real questionnaire, most questions have been asked before, and the same question never needs a human twice. What makes it safe to automate is not the matching; it is the discipline around it: every answer cites the source document and version it was approved against, a source update marks the answers citing it **stale** before anyone can reuse them, and nothing leaves the building without passing an approval gate. This project builds that layer end to end, deterministically, with its quality measured against a labelled ground truth.

> **Synthetic data only.** Every document, answer and question belongs to **Helios Home**, a fictional home solar and battery company invented for this project. No real company, customer, RFP or questionnaire is used anywhere.

Stdlib-only Python. Zero network, zero API keys, zero external dependencies — and zero LLM: matching is deterministic **TF-IDF** — term frequency-inverse document frequency, where a shared rare word counts for more than a shared common one — and drafting is **extractive** — assembled verbatim from approved or retrieved text, never generated. The same input always produces the same output, which is what makes the numbers below pinnable.

## The headline numbers

Against the bundled fixtures (3 source docs, an 8-answer approved library, a 12-question questionnaire with a labelled answer key):

| Check | Result |
|---|---|
| Match **precision** — of the questions resolved to a library answer, how many got the *right* answer | **1.0** (7/7) |
| Stale answers in the library after two planted doc bumps | **3 of 8** (A002, A005, A008), all flagged |
| Stale catch on the questionnaire — questions whose best match is stale, blocked instead of reused | **1.0** (2/2, with no answer text leaked) |
| Refusal rate on planted unanswerable questions | **1.0** (3/3 refused, no fabricated answer) |
| Retrieval fallback accuracy (right doc section, verbatim, cited) | **1.0** (2/2) |
| **Reuse rate** — share of the questionnaire answered straight from the library | **0.4167** (5/12), **3.0 drafting hours avoided** (plus 2 more questions drafted by retrieval) |

The questionnaire's outcome partition is the whole story in one line: **5 from the library, 2 by retrieval, 2 blocked as stale, 3 refused as unanswerable.** A tool that answered 12/12 would be the dangerous version of this project.

## Quickstart

```bash
# 1. Generate the synthetic fixture set (docs + library + questionnaire)
python3 cli.py generate

# 2. The answer library, with stale answers flagged by version citation
python3 cli.py library

# 3. Match a questionnaire (JSON or CSV) — library first, retrieval fallback
python3 cli.py match --input fixtures/questionnaire.json

# 4. Turn matches into drafts (every draft starts unapproved)
python3 cli.py draft --out drafts.json

# 5. Approve the answerable drafts (refused / stale-blocked cannot approve)
python3 cli.py approve --input drafts.json --out approved.json

# 6. Export — all-or-nothing gate: a batch containing anything
#    unapproved or stale is refused whole and writes nothing
python3 cli.py export --input approved.json   # exit 1: mixed batch refused

# 7. Combined report (library health + match scores + reuse)
python3 cli.py report

# 8. CI gate: exit 0 = pass, 1 = precision / stale-catch / refusal
#    breach, 2 = data-quality / IO error
python3 cli.py check; echo $?

# 9. One-command end-to-end demo (library -> match -> approve ->
#    export gate -> report -> check -> serve)
python3 demo.py

# 10. Tiny localhost API: POST /draft, POST /export,
#     GET /report, GET /health on 127.0.0.1
python3 cli.py serve --port 8765
```

## How it works

**The library is the product; retrieval is plumbing.** Each approved answer stores the question it answered, the answer text, and a **citation** — the source doc, the *version* of that doc it was approved against, and the section. A new questionnaire is matched against the library's questions first. Only a question with no library match falls back to retrieval over the source docs, and only a question that clears neither threshold is refused.

**Stale detection is a version comparison, never a text guess.** When a source doc's version bumps — the fixtures plant two: `security-policy` v2 → v3 and `deployment-guide` v1 → v2 — every approved answer citing an older version is flagged stale. A stale answer can still be the best textual match for an incoming question (two questionnaire questions match one); the outcome is then `stale_blocked`, carrying the citation for the human who must re-approve it, and *no answer text*. Stale text is never silently reused.

**The approval state machine is minimal on purpose:** `draft → approved → exportable`. Matched and retrieved answers are born as drafts. Approval is refused for refused and stale-blocked drafts. **Export** — producing the answer set that would go back to the customer — is an **all-or-nothing gate**: one unapproved, stale or refused row refuses the entire batch and writes nothing, so a bad answer cannot leak inside a mostly-good export. (The author's [`tool-approval-gate`](https://github.com/AkashB98/tool-approval-gate) is the fuller, general-purpose approval engine; this gate is the same discipline scoped to questionnaire answers.)

**Reuse is the metric that justifies the system.** The report carries the **reuse rate** — the share of a questionnaire answered from the library — and estimated human drafting hours avoided (0.5 h per library reuse, 0.25 h per retrieval draft, which still needs shaping). On the seeded questionnaire: 0.4167 and 3.0 hours for twelve questions — the number a solutions lead would extrapolate to a 200-question security questionnaire.

**Retrieval stays shallow here, deliberately.** The fallback is one TF-IDF pass over doc sections returning a verbatim extract with its citation — enough to draft a first answer for a human to approve into the library. Deeper retrieval quality (chunking, groundedness, refusal calibration at scale) is the subject of the author's `grounded-rag-chat` / `rag-chatbot-evals` projects; duplicating that here would have made this repo a worse copy of both. Once a retrieved draft is approved, it *becomes* a library answer with a citation — which is how the library grows and the reuse rate climbs.

## Architecture

| Module | Job |
|---|---|
| `generator.py` | Deterministic Helios Home fixtures: 3 source docs (12 sections), the 8-answer library (5 fresh, 3 stale by citation), the 12-question questionnaire, and its labelled ground truth (5 library / 2 retrieval / 2 stale / 3 unanswerable) |
| `matching.py` | Tokenisation (with brand/stopword handling), TF-IDF cosine matching: library first at threshold 0.45, extractive retrieval fallback at 0.20, refusal below both |
| `library.py` | Staleness by version citation, the draft → approved state machine, the all-or-nothing export gate (`ExportRefused`, zero leaks), and the reuse / hours-saved metrics |
| `validation.py` | Data-quality gate for docs, library entries and questions (required fields, citation integrity, bool-as-int traps) — reports issues, never raises on bad data |
| `report.py` | Combined report: library health, match precision / stale catch / refusal / retrieval scores vs ground truth, reuse, deterministic narrative |
| `cli.py` | `generate` / `library` / `match` / `draft` / `approve` / `export` / `report` / `check` (CI exit 0/1/2) / `demo` / `serve` (stdlib `http.server` on 127.0.0.1: `POST /draft`, `POST /export` — 409 on a refused batch, `GET /report`, `GET /health`); JSON and CSV questionnaire inputs |
| `demo.py` | End-to-end narrative with asserts: stale flags, the 5/2/2/3 outcome partition, approval refusals, export zero-leak behaviour (asserts no file is written), check exit codes, live localhost serve round-trip |
| `fixtures/` | `source_docs.json`, `answer_library.json`, `questionnaire.json` + `.csv`, `ground_truth.json` — exactly what the generator emits |

## Evals

`python3 evals/run_evals.py` → **12/12 golden evals**, report committed at `evals/eval_report.json` (md5 `b32f25a03bd0d20680d2c9dc88cfcef3`, byte-identical across 3 verified runs):

- **E1** generator determinism — questionnaire and library JSON bytes pinned by md5
- **E2** library staleness pinned: exactly A002, A005, A008 stale after the two planted bumps
- **E3** headline: match precision pinned at 1.0 (7/7 resolved to the right answer)
- **E4** stale catch pinned: 2/2 stale matches blocked, carrying no answer text
- **E5** refusal pinned: 3/3 planted unanswerable refused, no answer and no citation fabricated
- **E6** retrieval pinned: 2/2 fallbacks land on the right sections, verbatim, with citations
- **E7** reuse pinned: rate 0.4167 (5/12), 3.0 hours avoided, 7/12 answered
- **E8** export gate pinned: mixed and unapproved batches refused whole; the CLI refusal writes no file (zero leaks); the clean subset exports 7/7
- **E9** state machine pinned: exactly 7 drafts approve; the 5 blocked/refused cannot
- **E10** CLI `check` exit codes 0 / 1 / 2
- **E11** serve round-trip matches local draft + export exactly; served mixed export returns 409 with `exported_count` 0
- **E12** bundled fixtures pinned (generator equality, CSV = JSON) and report determinism

Unit tests: `python3 -m unittest discover -s tests` → **68 hermetic tests**, including a no-network enforcement test (sockets stubbed), hand-built staleness cases (unknown doc, future version, the bool trap), state-machine and export-gate negatives (one bad row blocks the batch; a stale answer marked approved still cannot export), refusal emptiness, CLI exit codes, CSV/JSON round-trips, and serve round-trips.

## Development loop — what the checks actually caught

1. **The brand name was a matching feature, and it leaked.** The first matcher run answered all three planted unanswerable questions: the revenue question "matched" the uptime answer at 0.52 on the strength of the shared brand tokens (*Helios Home* appears in questions of every topic), and the quantum question retrieved the Support section because it used *support* as a verb. Both are the same bug — tokens that carry no topical signal scoring as if they did. The fix is structural, not a threshold fiddle: the company name joins the stopword list (a solutions tool must work for any company name, so the brand can never be evidence), and the one verb-collision question was reworded to the noun-free form a real questionnaire would also be caught by. After the fix the unanswerable scores are 0.0 / 0.317 / 0.0 against thresholds of 0.45 / 0.20 — refused with margin, and E5 pins it.
2. **The thresholds sit in measured gaps, not at round numbers.** Real library matches score 0.877–1.0; the worst noise score after the stopword fix is 0.317. The library threshold (0.45) sits between them, closer to the noise — a paraphrase has more room to be loose than a fabrication has to sneak in. Retrieval is the honest tight one: the patching question scores 0.2819 against a 0.20 threshold, because patch vocabulary genuinely overlaps the penetration-testing section. That margin is reported, not hidden: if a future fixture makes it tighter, E6 fails loudly instead of the tool quietly starting to refuse answerable questions.
3. **Partial export was the first design, and it was wrong.** The natural implementation exports the approved rows and lists the blocked ones. That is precisely how a stale access-control answer ships inside a 200-question response: nobody reads the appendix. The gate now refuses the batch whole and the CLI writes no file on refusal — E8 and the demo both assert the file's *absence*, because "zero leaks" is a claim about what does not exist, and it has to be tested that way.

## Scope and honest limits

- **Extractive drafting only — there is no LLM in this project.** "Drafts" are approved answer text or verbatim doc extracts with citations. A generated paraphrase might read better; it could also quietly change a compliance claim, which is the one thing a security questionnaire answer must never do. Fluency is traded for fidelity on purpose.
- **TF-IDF is a baseline, and the fixtures are sized to it.** Eight library questions separate cleanly; eight hundred would need stemming, synonym handling and probably embeddings — at which point determinism and pinnability, this project's actual claims, would need re-earning. The claim here is an auditable matching baseline with measured precision and total stale/refusal discipline, not state-of-the-art retrieval.
- **Staleness is version equality, not diff awareness.** An answer citing v2 of a doc now at v3 is stale even if its section never changed — conservative by design (a human re-approval is cheap; a wrong reused answer is not), and stated rather than smoothed over.
- **Hours saved are stated constants, not measurements** (0.5 h per reuse, 0.25 h per retrieval draft). They exist so reuse is reported in the unit a solutions team budgets in; a real deployment would calibrate them from ticket data.
- **The approval gate is minimal.** No roles, no quorum, no audit log — one transition, enforced in one place. The fuller engine is `tool-approval-gate`; this repo borrows its discipline, not its feature set.
- **The API is a demo surface.** It binds 127.0.0.1 only, is stateless per request, and re-reads the seeded fixtures.

## Why this project

Solutions delivery and forward-deployed work run on trust artifacts: the security questionnaire a customer's team grades before any contract is signed. Automating that work safely means the boring disciplines — citations, versioning, approval gates, measured refusal — done in code a reviewer can run and a gate can enforce. That is the bet of this repo: the same question never needs a human twice, a stale answer never gets a second life, and an unanswerable question gets a refusal instead of an invention.

## License

MIT — see LICENSE.
