"""Deterministic synthetic fixtures for Helios Home (fictional).

SYNTHETIC DATA ONLY — Helios Home is a fictional home solar and
battery company invented for this project. No real company, customer,
RFP or security questionnaire is used anywhere.

The generator emits three fixture families:

* source docs (3 documents) — the fictional source of truth every
  answer must cite. Two documents carry a planted version bump:
  ``security-policy`` v2 -> v3 and ``deployment-guide`` v1 -> v2.
  The current version of each doc is the one in this file.
* the approved answer library (8 entries) — previously approved
  answers, each citing a source doc + version + section. 5 cite the
  current version (fresh); 3 cite a superseded version (stale):
  A002 (security-policy v2), A005 (deployment-guide v1) and
  A008 (security-policy v1). Staleness is a version comparison,
  never a text guess.
* a questionnaire (12 questions) with a labelled ground truth:
  5 questions match a fresh approved answer, 2 match a stale
  approved answer (and must be blocked, not reused), 2 need
  extractive retrieval over the source docs, and 3 are planted
  UNANSWERABLE (no library match, nothing in the docs — the only
  correct behaviour is refusal, never fabrication).
"""

from __future__ import annotations

import csv
import io
import json
from typing import Dict, List


def _section(section_id, heading, text):
    return {"section_id": section_id, "heading": heading, "text": text}


def _doc(doc_id, title, version, sections):
    return {"doc_id": doc_id, "title": title, "version": version,
            "sections": sections}


def generate_docs() -> List[Dict]:
    return [
        _doc("security-policy", "Helios Home Security Policy", 3, [
            _section("encryption", "Encryption at rest and in transit",
                     "All customer data is encrypted at rest using "
                     "AES-256 and in transit using TLS 1.3. Encryption "
                     "keys are rotated every 90 days and managed in a "
                     "dedicated hardware-backed key service."),
            _section("access-control",
                     "Authentication and access control",
                     "Access to production systems requires single "
                     "sign-on with multi-factor authentication and "
                     "role-based access control. Privileged access is "
                     "reviewed quarterly and all access is logged to "
                     "the central audit log."),
            _section("incident-response",
                     "Incident response and breach notification",
                     "Helios Home maintains a documented incident "
                     "response plan that is tested twice each year. "
                     "Customers are notified within 72 hours of a "
                     "confirmed breach affecting their data."),
            _section("backup-retention", "Backups and retention",
                     "Backups are taken daily and retained for 35 "
                     "days. Restore tests are performed monthly. "
                     "Backups are encrypted and stored in a separate "
                     "region from production data."),
            _section("penetration-testing", "Penetration testing",
                     "Helios Home engages an independent firm for "
                     "annual penetration testing of the customer "
                     "portal and installer platform, alongside "
                     "continuous vulnerability scanning. Critical "
                     "findings are remediated within 30 days."),
            _section("patching", "Patch management",
                     "Security patches for critical vulnerabilities "
                     "are applied within 7 days of release and high "
                     "severity patches within 30 days. Servers are "
                     "scanned weekly for missing patches."),
        ]),
        _doc("deployment-guide", "Helios Home Deployment Guide", 2, [
            _section("uptime-sla", "Uptime and service levels",
                     "Helios Home guarantees 99.9 percent monthly "
                     "uptime for the customer portal and installer "
                     "platform, excluding scheduled maintenance, "
                     "with service credits when the target is missed."),
            _section("onboarding", "Onboarding timeline",
                     "Standard onboarding takes 2 to 3 weeks and "
                     "includes data migration, installer training and "
                     "a dedicated onboarding manager for the first "
                     "30 days."),
            _section("data-residency", "Data residency and hosting",
                     "Customer data is hosted in the United States "
                     "in the us-east-1 and us-west-2 cloud regions. "
                     "Customer data does not leave the United States "
                     "without written customer consent."),
            _section("support", "Support hours",
                     "Support is available around the clock for "
                     "critical incidents, with a one hour response "
                     "target, and during business hours for standard "
                     "requests."),
        ]),
        _doc("compliance-overview", "Helios Home Compliance Overview", 1, [
            _section("dpa-subprocessors",
                     "Data processing and subprocessors",
                     "Helios Home offers a Data Processing Agreement "
                     "on request and maintains a public list of "
                     "subprocessors. The subprocessor list is updated "
                     "at least 30 days before any new subprocessor "
                     "processes customer data."),
            _section("certifications", "Certifications and audits",
                     "Helios Home is audited annually against the "
                     "SOC 2 Type II criteria covering security, "
                     "availability and confidentiality."),
        ]),
    ]


def _answer(answer_id, question, answer_text, doc_id, version, section_id):
    return {"answer_id": answer_id, "question": question,
            "answer": answer_text, "source_doc": doc_id,
            "source_version": version, "source_section": section_id,
            "status": "approved"}


def generate_library() -> List[Dict]:
    return [
        _answer("A001",
                "How is customer data encrypted at rest and in transit?",
                "All customer data is encrypted at rest using AES-256 "
                "and in transit using TLS 1.3. Encryption keys are "
                "rotated every 90 days.",
                "security-policy", 3, "encryption"),
        _answer("A002",
                "What authentication and access controls protect "
                "production systems?",
                "Access to production systems requires single sign-on "
                "with multi-factor authentication and role-based access "
                "control. Privileged access is reviewed quarterly.",
                "security-policy", 2, "access-control"),
        _answer("A003",
                "How do you handle incident response and breach "
                "notification?",
                "Helios Home maintains a documented incident response "
                "plan tested twice each year. Customers are notified "
                "within 72 hours of a confirmed breach affecting "
                "their data.",
                "security-policy", 3, "incident-response"),
        _answer("A004",
                "What uptime SLA does Helios Home guarantee?",
                "Helios Home guarantees 99.9 percent monthly uptime "
                "for the customer portal and installer platform, "
                "excluding scheduled maintenance.",
                "deployment-guide", 2, "uptime-sla"),
        _answer("A005",
                "How long does onboarding take?",
                "Standard onboarding takes 2 to 3 weeks and includes "
                "data migration and installer training.",
                "deployment-guide", 1, "onboarding"),
        _answer("A006",
                "Where is customer data stored and hosted?",
                "Customer data is hosted in the United States in the "
                "us-east-1 and us-west-2 cloud regions and does not "
                "leave the United States without written consent.",
                "deployment-guide", 2, "data-residency"),
        _answer("A007",
                "Do you offer a Data Processing Agreement and list "
                "your subprocessors?",
                "Helios Home offers a Data Processing Agreement on "
                "request and maintains a public list of subprocessors, "
                "updated at least 30 days before any new subprocessor "
                "processes customer data.",
                "compliance-overview", 1, "dpa-subprocessors"),
        _answer("A008",
                "How often are backups taken and how long are they "
                "retained?",
                "Backups are taken daily and retained for 35 days. "
                "Restore tests are performed monthly.",
                "security-policy", 1, "backup-retention"),
    ]


def _q(qid, question):
    return {"qid": qid, "question": question}


def generate_questionnaire() -> List[Dict]:
    return [
        _q("Q01", "How is customer data encrypted at rest and in transit?"),
        _q("Q02", "In which regions is customer data hosted and stored?"),
        _q("Q03", "What uptime SLA do you guarantee for the Helios platform?"),
        _q("Q04", "Do you offer a Data Processing Agreement and maintain "
                 "a list of subprocessors?"),
        _q("Q05", "How do you handle incident response and breach "
                 "notification to customers?"),
        _q("Q06", "How often do you conduct penetration testing and "
                 "vulnerability scanning?"),
        _q("Q07", "What is your patching cadence for critical security "
                 "vulnerabilities?"),
        _q("Q08", "How often are backups taken and how long are they "
                 "retained?"),
        _q("Q09", "What authentication and access controls protect "
                 "production systems?"),
        _q("Q10", "What is the home address and personal phone number "
                 "of your chief executive?"),
        _q("Q11", "Do you offer quantum blockchain mainframe "
                 "teleportation sync?"),
        _q("Q12", "What was Helios Home total revenue and profit "
                 "margin in 2019?"),
    ]


def generate_ground_truth() -> Dict:
    """The labelled answer key for the questionnaire.

    kind: ``library`` (fresh approved match), ``stale`` (matches an
    approved answer whose citation is stale — must be blocked),
    ``retrieval`` (no library match; answerable extractively from
    the named doc section), ``unanswerable`` (must be refused).
    """
    return {"cases": [
        {"qid": "Q01", "kind": "library", "answer_id": "A001"},
        {"qid": "Q02", "kind": "library", "answer_id": "A006"},
        {"qid": "Q03", "kind": "library", "answer_id": "A004"},
        {"qid": "Q04", "kind": "library", "answer_id": "A007"},
        {"qid": "Q05", "kind": "library", "answer_id": "A003"},
        {"qid": "Q06", "kind": "retrieval", "doc_id": "security-policy",
         "section_id": "penetration-testing"},
        {"qid": "Q07", "kind": "retrieval", "doc_id": "security-policy",
         "section_id": "patching"},
        {"qid": "Q08", "kind": "stale", "answer_id": "A008"},
        {"qid": "Q09", "kind": "stale", "answer_id": "A002"},
        {"qid": "Q10", "kind": "unanswerable"},
        {"qid": "Q11", "kind": "unanswerable"},
        {"qid": "Q12", "kind": "unanswerable"},
    ]}


# ------------------------------------------------------------ serialise

def docs_to_json(docs: List[Dict]) -> str:
    return json.dumps(docs, indent=2, sort_keys=True) + "\n"


def library_to_json(library: List[Dict]) -> str:
    return json.dumps(library, indent=2, sort_keys=True) + "\n"


def questionnaire_to_json(questions: List[Dict]) -> str:
    return json.dumps(questions, indent=2, sort_keys=True) + "\n"


def questionnaire_to_csv(questions: List[Dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["qid", "question"])
    writer.writeheader()
    for q in questions:
        writer.writerow({"qid": q["qid"], "question": q["question"]})
    return buf.getvalue()


def ground_truth_to_json(truth: Dict) -> str:
    return json.dumps(truth, indent=2, sort_keys=True) + "\n"
