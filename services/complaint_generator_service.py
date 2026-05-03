"""
Complaint draft generator — Phase 3.

Consumes build_legal_results() output and produces a structured federal complaint
draft with per-section text and [FACT NEEDED: ...] placeholders for missing facts.

This is a legal information and drafting tool, not legal advice.
Controlling authority referenced throughout:
  - Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992) — standing
  - TransUnion LLC v. Ramirez, 594 U.S. 413 (2021) — concrete harm
  - Kentucky v. Graham, 473 U.S. 159 (1985) — capacity
  - Ex parte Young, 209 U.S. 123 (1908) — injunctive relief / sovereign immunity
  - Monell v. Dept. of Social Services, 436 U.S. 658 (1978) — municipal liability
  - 42 U.S.C. §1983 — civil rights remedy
  - 28 U.S.C. §1331 — federal question jurisdiction
  - 28 U.S.C. §1343 — civil rights jurisdiction
  - 28 U.S.C. §1391 — venue
"""
from typing import Any, Dict, List, Optional

from services.legal_results_service import build_legal_results, LegalResultsServiceError


DISCLAIMER = (
    "DRAFT FOR LEGAL INFORMATION AND REVIEW ONLY. "
    "This document is not legal advice, does not create an attorney-client relationship, "
    "and should not be filed without review by a licensed attorney."
)


class ComplaintGeneratorServiceError(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _need(label: str) -> str:
    return f"[FACT NEEDED: {label}]"


def _get_plaintiff(intake_state: Dict[str, Any]) -> Dict[str, str]:
    profile = intake_state.get("identityProfile", {}) or {}
    addr = profile.get("residentialAddress", {}) or {}
    return {
        "name": profile.get("fullLegalName", "") or _need("plaintiff full legal name"),
        "email": profile.get("email", "") or "",
        "phone": profile.get("phone", "") or "",
        "street": addr.get("street1", "") or "",
        "city": addr.get("city", "") or "",
        "state": addr.get("state", "") or "",
        "zip": addr.get("postalCode", "") or "",
    }


def _get_complaint_record(intake_state: Dict[str, Any], complaint_id: Optional[str]) -> Dict[str, Any]:
    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    if not complaints:
        return {}
    if complaint_id:
        return next((c for c in complaints if c.get("complaintId") == complaint_id), complaints[0])
    return complaints[0]


def _missing(value: Any) -> bool:
    return not value or (isinstance(value, str) and value.startswith("[FACT NEEDED"))


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_caption(plaintiff: Dict[str, str], results: Dict[str, Any]) -> Dict[str, Any]:
    recommended_court = results.get("jurisdiction", {}).get("recommended_court", "")
    if recommended_court == "federal_district":
        court_line = f"IN THE UNITED STATES DISTRICT COURT\nFOR THE {_need('specify federal district, e.g., D. Md. / E.D.N.Y.')}"
    else:
        court_line = (
            "STATE COURT REVIEW NEEDED — federal jurisdiction not confirmed. "
            "File in the appropriate state trial court of general jurisdiction. "
            f"(Jurisdiction analysis returned: '{recommended_court}')"
        )

    plaintiff_name = plaintiff["name"]
    target_name = results.get("capacity", {}).get("recommended_defendants", [])
    defendant_block = "\n".join(target_name) if target_name else _need("defendant(s) full legal name(s) and capacity designation")

    text = (
        f"{court_line}\n\n"
        f"{plaintiff_name},\n    Plaintiff,\n\n"
        f"v.\n\n"
        f"{defendant_block},\n    Defendant(s).\n\n"
        f"Case No.: [TO BE ASSIGNED BY COURT]\n\n"
        f"COMPLAINT\n"
        f"(Jury Trial Demanded)"
    )
    return {"title": "Caption", "text": text}


def _build_parties(plaintiff: Dict[str, str], complaint: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
    lines: List[str] = []
    para = 1

    # Plaintiff
    p_addr = ""
    parts = [plaintiff.get("street"), plaintiff.get("city"), plaintiff.get("state"), plaintiff.get("zip")]
    p_addr_parts = [p for p in parts if p and not _missing(p)]
    p_addr = ", ".join(p_addr_parts) if p_addr_parts else _need("plaintiff residential address")

    lines.append(
        f"{para}. Plaintiff {plaintiff['name']} is an individual residing at {p_addr}."
    )
    para += 1

    # Defendants from capacity analysis
    capacity = results.get("capacity", {})
    individual = capacity.get("capacity_split", {}).get("individual", [])
    official = capacity.get("capacity_split", {}).get("official", [])
    target_name = complaint.get("targetName", "") or _need("defendant entity name")
    target_person = complaint.get("targetPerson", "") or ""
    target_dept = complaint.get("targetDepartment", "") or ""
    target_type = capacity.get("target_type", "private")

    if individual:
        for ind in individual:
            lines.append(
                f"{para}. Defendant {ind} is sued in their individual capacity for personal liability "
                f"under 42 U.S.C. §1983. Hafer v. Melo, 502 U.S. 21 (1991)."
            )
            para += 1

    if official:
        for off in official:
            ex_parte = capacity.get("ex_parte_young_available", False)
            relief_note = (
                " Injunctive relief is sought against this Defendant in their official capacity pursuant to "
                "Ex parte Young, 209 U.S. 123 (1908)."
                if ex_parte else ""
            )
            lines.append(
                f"{para}. Defendant {off} is sued in their official capacity as a representative of "
                f"{target_name}.{relief_note}"
            )
            para += 1

    if not individual and not official:
        lines.append(
            f"{para}. Defendant {target_name} is a "
            + ("government entity or public agency" if target_type == "government" else "private entity")
            + f" operating in {_need('state/jurisdiction')}."
        )
        para += 1

    return {
        "title": "Parties",
        "paragraph_start": 1,
        "text": "\n\n".join(lines),
        "paragraph_count": para - 1,
    }


def _build_jurisdiction_venue(results: Dict[str, Any], para_start: int) -> Dict[str, Any]:
    juris = results.get("jurisdiction", {})
    federal_q = juris.get("federal_question", False)
    civil_rights_j = juris.get("civil_rights_jurisdiction", False)
    recommended_court = juris.get("recommended_court", "")
    venue_notes = juris.get("venue_notes", "") or _need("venue determination — identify district where events occurred")

    lines: List[str] = []
    para = para_start

    if recommended_court != "federal_district":
        lines.append(
            f"{para}. NOTE: Federal jurisdiction analysis returned '{recommended_court}'. "
            "State court may be the appropriate forum. The following jurisdiction allegations are "
            "presented for review and should be confirmed before filing in federal court."
        )
        para += 1

    if federal_q:
        lines.append(
            f"{para}. This Court has subject matter jurisdiction pursuant to 28 U.S.C. §1331 "
            "because this civil action arises under the Constitution and laws of the United States. "
            "Merrell Dow Pharmaceuticals v. Thompson, 478 U.S. 804 (1986)."
        )
        para += 1

    if civil_rights_j:
        lines.append(
            f"{para}. This Court also has jurisdiction pursuant to 28 U.S.C. §1343(a)(3) because "
            "Plaintiff seeks to redress the deprivation of rights, privileges, and immunities secured "
            "by the Constitution of the United States and federal law, committed under color of state "
            "law, within the meaning of 42 U.S.C. §1983."
        )
        para += 1

    if not federal_q and not civil_rights_j:
        lines.append(
            f"{para}. {_need('identify basis for federal subject matter jurisdiction — §1331 (federal question) or §1343 (civil rights) or §1332 (diversity)')}"
        )
        para += 1

    lines.append(
        f"{para}. Venue is proper in this district pursuant to 28 U.S.C. §1391(b) because "
        f"a substantial part of the events or omissions giving rise to Plaintiff's claims occurred "
        f"within this district. {venue_notes}"
    )
    para += 1

    return {
        "title": "Jurisdiction and Venue",
        "paragraph_start": para_start,
        "text": "\n\n".join(lines),
        "paragraph_count": para - para_start,
        "statutes": ["28 U.S.C. §1331", "28 U.S.C. §1343", "28 U.S.C. §1391(b)"],
    }


def _build_standing(results: Dict[str, Any], para_start: int) -> Dict[str, Any]:
    standing = results.get("standing", {})
    injury = standing.get("injury_in_fact", {})
    causation = standing.get("causation", {})
    redressability = standing.get("redressability", {})

    lines: List[str] = []
    para = para_start

    lines.append(
        f"{para}. Plaintiff has Article III standing to bring this action pursuant to "
        "Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992), which requires (1) an injury in fact "
        "that is concrete, particularized, and actual or imminent; (2) a causal connection between "
        "the injury and the challenged conduct; and (3) a likelihood that the injury will be "
        "redressed by a favorable decision."
    )
    para += 1

    injury_text = injury.get("analysis", "") or _need("injury in fact description — concrete, particularized harm suffered by plaintiff")
    lines.append(
        f"{para}. Injury in Fact: {injury_text} "
        "Under TransUnion LLC v. Ramirez, 594 U.S. 413 (2021), Plaintiff's alleged harm constitutes "
        "concrete injury beyond a bare procedural violation."
    )
    para += 1

    harms = injury.get("concrete_harms", [])
    if harms:
        harms_clean = [h for h in harms if "weak" not in h.lower() and "insufficient" not in h.lower()]
        if harms_clean:
            lines.append(
                f"{para}. Plaintiff's concrete harms include: "
                + "; ".join(harms_clean[:3]) + "."
            )
            para += 1

    causation_text = causation.get("analysis", "") or _need("causation — describe how defendant's conduct caused plaintiff's injury")
    lines.append(f"{para}. Causation: {causation_text}")
    para += 1

    redressability_text = redressability.get("analysis", "") or _need("redressability — state the relief requested and how a court ruling would address the injury")
    lines.append(f"{para}. Redressability: {redressability_text}")
    para += 1

    return {
        "title": "Standing",
        "paragraph_start": para_start,
        "text": "\n\n".join(lines),
        "paragraph_count": para - para_start,
        "standing_established": standing.get("established", False),
        "case_law": ["Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992)", "TransUnion LLC v. Ramirez, 594 U.S. 413 (2021)"],
    }


def _build_facts(complaint: Dict[str, Any], para_start: int) -> Dict[str, Any]:
    what_happened = complaint.get("whatHappened", "") or ""
    summary = complaint.get("plainLanguageSummary", "") or ""
    what_was_said = complaint.get("whatWasSaid", "") or ""
    user_actions = complaint.get("userActionsTaken", []) or []
    timeline = complaint.get("timelineEvents", []) or []
    financial_loss = complaint.get("financialLossAmount", 0) or 0
    target_name = complaint.get("targetName", "") or _need("defendant name")

    lines: List[str] = []
    para = para_start

    narrative = what_happened or summary
    if narrative:
        lines.append(f"{para}. {narrative}")
    else:
        lines.append(f"{para}. {_need('factual narrative — describe what happened, when, where, and who was involved')}")
    para += 1

    if what_was_said:
        lines.append(f"{para}. {target_name} stated or communicated: \"{what_was_said}\"")
        para += 1

    if timeline:
        for event in timeline[:5]:
            date = event.get("date", _need("event date"))
            description = event.get("description", "") or event.get("event", _need("event description"))
            lines.append(f"{para}. On or about {date}, {description}")
            para += 1
    else:
        lines.append(f"{para}. {_need('timeline — list key dates and events in chronological order')}")
        para += 1

    if user_actions:
        lines.append(
            f"{para}. Plaintiff took the following actions prior to filing: "
            + "; ".join(str(a) for a in user_actions[:5]) + "."
        )
        para += 1

    if float(financial_loss) > 0:
        lines.append(
            f"{para}. As a direct and proximate result of Defendant's conduct, Plaintiff suffered "
            f"financial loss in an amount of not less than ${float(financial_loss):,.2f}, plus consequential "
            "damages to be determined at trial."
        )
        para += 1

    return {
        "title": "Statement of Facts",
        "paragraph_start": para_start,
        "text": "\n\n".join(lines),
        "paragraph_count": para - para_start,
    }


def _build_capacity_defendants(results: Dict[str, Any], complaint: Dict[str, Any], para_start: int) -> Dict[str, Any]:
    capacity = results.get("capacity", {})
    individual = capacity.get("capacity_split", {}).get("individual", [])
    official = capacity.get("capacity_split", {}).get("official", [])
    ex_parte = capacity.get("ex_parte_young_available", False)
    sovereign_immunity = capacity.get("sovereign_immunity_applies", False)
    immunity_notes = capacity.get("immunity_notes", [])
    target_type = capacity.get("target_type", "private")

    lines: List[str] = []
    para = para_start

    lines.append(
        f"{para}. The capacity in which each Defendant is sued is governed by "
        "Kentucky v. Graham, 473 U.S. 159 (1985), which held that a suit against a government "
        "official in their official capacity is a suit against the governmental entity itself, "
        "while a suit in individual capacity seeks to impose personal liability on the officer."
    )
    para += 1

    if individual:
        lines.append(
            f"{para}. The following Defendant(s) are sued in their individual (personal) capacity: "
            + ", ".join(individual) + ". "
            "Personal liability under 42 U.S.C. §1983 for individual-capacity defendants was confirmed "
            "in Hafer v. Melo, 502 U.S. 21 (1991)."
        )
        para += 1

    if official:
        lines.append(
            f"{para}. The following Defendant(s) are sued in their official capacity: "
            + ", ".join(official) + ". "
            "An official-capacity §1983 claim functions as a claim against the governmental entity."
        )
        para += 1

    if sovereign_immunity:
        lines.append(
            f"{para}. Defendant's sovereign immunity defense: "
            + (immunity_notes[0] if immunity_notes else
               "The Eleventh Amendment bars retrospective damages against the State in federal court. "
               "Will v. Michigan Dept. of State Police, 491 U.S. 58 (1989). "
               "Plaintiff must seek damages from individually named officers.")
        )
        para += 1

    if ex_parte:
        lines.append(
            f"{para}. Plaintiff seeks prospective injunctive relief against Defendant(s) in their "
            "official capacity pursuant to Ex parte Young, 209 U.S. 123 (1908), which held that "
            "the Eleventh Amendment does not bar suits against state officers seeking prospective "
            "relief to end ongoing constitutional violations."
        )
        para += 1

    if not individual and not official and target_type == "private":
        target_name = complaint.get("targetName", "") or _need("defendant entity name")
        lines.append(
            f"{para}. Defendant {target_name} is a private actor. Standard entity and individual "
            "liability rules apply. No Eleventh Amendment sovereign immunity issues arise."
        )
        para += 1

    return {
        "title": "Capacity and Defendant Identification",
        "paragraph_start": para_start,
        "text": "\n\n".join(lines),
        "paragraph_count": para - para_start,
        "case_law": ["Kentucky v. Graham, 473 U.S. 159 (1985)", "Ex parte Young, 209 U.S. 123 (1908)"],
    }


def _build_causes_of_action(results: Dict[str, Any], complaint: Dict[str, Any], para_start: int) -> Dict[str, Any]:
    rights = results.get("rights", {})
    claims = rights.get("claims", [])
    violations = rights.get("constitutional_violations", [])
    municipal = rights.get("municipal_liability", False)
    municipal_analysis = rights.get("municipal_liability_analysis", "")
    target_name = complaint.get("targetName", "") or _need("defendant name")

    lines: List[str] = []
    para = para_start
    count = 1

    has_1983 = any(c.get("type", "").startswith("§1983") for c in claims)
    has_4th = any(v.get("amendment") == "Fourth Amendment" for v in violations)
    has_14th_dp = any(v.get("amendment") == "Fourteenth Amendment" and "Due Process" in v.get("clause", "") for v in violations)
    has_14th_ep = any(v.get("amendment") == "Fourteenth Amendment" and "Equal Protection" in v.get("clause", "") for v in violations)
    has_fcra = any(c.get("type") == "FCRA Claim" for c in claims)
    has_fdcpa = any(c.get("type") == "FDCPA Claim" for c in claims)
    has_contract = any("Contract" in c.get("type", "") or "Breach" in c.get("type", "") for c in claims)

    if has_1983:
        section_1983_claim = next((c for c in claims if c.get("type", "").startswith("§1983")), {})
        basis = section_1983_claim.get("basis", "") or _need("§1983 basis — describe the constitutional deprivation")
        lines.append(f"COUNT {count} — 42 U.S.C. §1983: CIVIL RIGHTS VIOLATION\n")
        lines.append(
            f"{para}. Plaintiff realleges and incorporates the foregoing paragraphs."
        )
        para += 1
        lines.append(
            f"{para}. At all relevant times, Defendant(s) acted under color of state law within "
            "the meaning of 42 U.S.C. §1983. West v. Atkins, 487 U.S. 42 (1988)."
        )
        para += 1
        lines.append(
            f"{para}. Defendant(s) deprived Plaintiff of rights, privileges, and immunities "
            f"secured by the Constitution and laws of the United States. {basis}"
        )
        para += 1
        count += 1

    if has_4th:
        fourth = next((v for v in violations if v.get("amendment") == "Fourth Amendment"), {})
        analysis = fourth.get("analysis", "") or _need("Fourth Amendment analysis")
        lines.append(f"\nCOUNT {count} — FOURTH AMENDMENT: UNREASONABLE SEARCH AND SEIZURE\n")
        lines.append(f"{para}. Plaintiff realleges and incorporates the foregoing paragraphs.")
        para += 1
        lines.append(
            f"{para}. Defendant(s) conducted an unreasonable search and/or seizure of Plaintiff's "
            f"person or property in violation of the Fourth Amendment to the United States Constitution. "
            f"{analysis}"
        )
        para += 1
        count += 1

    if has_14th_dp:
        fourteenth_dp = next((v for v in violations if "Due Process" in v.get("clause", "")), {})
        analysis = fourteenth_dp.get("analysis", "") or _need("Fourteenth Amendment due process analysis")
        clause = fourteenth_dp.get("clause", "Due Process")
        lines.append(f"\nCOUNT {count} — FOURTEENTH AMENDMENT: {clause.upper()}\n")
        lines.append(f"{para}. Plaintiff realleges and incorporates the foregoing paragraphs.")
        para += 1
        lines.append(
            f"{para}. Defendant(s) deprived Plaintiff of life, liberty, or property without "
            f"due process of law in violation of the Fourteenth Amendment. {analysis}"
        )
        para += 1
        count += 1

    if has_14th_ep:
        lines.append(f"\nCOUNT {count} — FOURTEENTH AMENDMENT: EQUAL PROTECTION\n")
        lines.append(f"{para}. Plaintiff realleges and incorporates the foregoing paragraphs.")
        para += 1
        lines.append(
            f"{para}. Defendant(s) treated Plaintiff differently from similarly situated individuals "
            "without a rational basis, or on the basis of a protected classification, in violation of "
            "the Equal Protection Clause of the Fourteenth Amendment."
        )
        para += 1
        count += 1

    if municipal:
        lines.append(f"\nCOUNT {count} — MONELL MUNICIPAL LIABILITY\n")
        lines.append(f"{para}. Plaintiff realleges and incorporates the foregoing paragraphs.")
        para += 1
        lines.append(
            f"{para}. {target_name}, as a municipality or local government entity, is liable under "
            "42 U.S.C. §1983 pursuant to Monell v. Dept. of Social Services, 436 U.S. 658 (1978). "
            f"{municipal_analysis or _need('allege specific policy, custom, or failure-to-train that was the moving force behind the constitutional violation')}"
        )
        para += 1
        count += 1

    if has_fcra:
        fcra_claim = next((c for c in claims if c.get("type") == "FCRA Claim"), {})
        lines.append(f"\nCOUNT {count} — FAIR CREDIT REPORTING ACT, 15 U.S.C. §1681\n")
        lines.append(f"{para}. Plaintiff realleges and incorporates the foregoing paragraphs.")
        para += 1
        lines.append(
            f"{para}. {fcra_claim.get('analysis', _need('FCRA violation description'))}"
        )
        para += 1
        count += 1

    if has_fdcpa:
        fdcpa_claim = next((c for c in claims if c.get("type") == "FDCPA Claim"), {})
        lines.append(f"\nCOUNT {count} — FAIR DEBT COLLECTION PRACTICES ACT, 15 U.S.C. §1692\n")
        lines.append(f"{para}. Plaintiff realleges and incorporates the foregoing paragraphs.")
        para += 1
        lines.append(
            f"{para}. {fdcpa_claim.get('analysis', _need('FDCPA violation description'))}"
        )
        para += 1
        count += 1

    if has_contract:
        contract_claim = next((c for c in claims if "Contract" in c.get("type", "") or "Breach" in c.get("type", "")), {})
        lines.append(f"\nCOUNT {count} — BREACH OF CONTRACT / UNJUST ENRICHMENT\n")
        lines.append(f"{para}. Plaintiff realleges and incorporates the foregoing paragraphs.")
        para += 1
        lines.append(
            f"{para}. {contract_claim.get('analysis', _need('breach of contract or unjust enrichment description'))}"
        )
        para += 1
        count += 1

    if not claims and not violations:
        lines.append(
            f"COUNT 1 — {_need('identify cause of action — no claims detected from intake. Specify constitutional amendment or statute violated.')}\n"
        )
        lines.append(
            f"{para}. {_need('factual basis for this count — describe the specific conduct and the right violated')}"
        )
        para += 1

    return {
        "title": "Causes of Action",
        "paragraph_start": para_start,
        "text": "\n\n".join(lines),
        "paragraph_count": para - para_start,
        "count_total": count - 1,
    }


def _build_prayer_for_relief(results: Dict[str, Any], complaint: Dict[str, Any]) -> Dict[str, Any]:
    rights = results.get("rights", {})
    capacity = results.get("capacity", {})
    standing = results.get("standing", {})
    has_1983 = any(c.get("type", "").startswith("§1983") for c in rights.get("claims", []))
    ex_parte = capacity.get("ex_parte_young_available", False)
    seeks_injunction = bool(complaint.get("desiredOutcome", "") and any(
        t in (complaint.get("desiredOutcome", "") or "").lower()
        for t in ["stop", "injunction", "cease", "enjoin", "prevent", "policy"]
    ))
    financial_loss = float(complaint.get("financialLossAmount", 0) or 0)

    items: List[str] = []

    if financial_loss > 0:
        items.append(
            f"(a) Compensatory damages in an amount not less than ${financial_loss:,.2f}, "
            "plus additional compensatory damages to be proven at trial;"
        )
    else:
        items.append(f"(a) Compensatory damages in an amount to be determined at trial;")

    items.append("(b) Punitive damages against the individual Defendant(s) to deter future misconduct;")

    if ex_parte or seeks_injunction:
        items.append(
            "(c) Preliminary and permanent injunctive relief pursuant to Ex parte Young, "
            "209 U.S. 123 (1908), enjoining Defendant(s) from continuing the unconstitutional "
            "policy, practice, or conduct described herein;"
        )

    items.append(
        "(d) Declaratory relief pursuant to 28 U.S.C. §2201, declaring that Defendant(s)' "
        "conduct violates Plaintiff's constitutional rights;"
    )

    if has_1983:
        items.append(
            "(e) Reasonable attorney's fees and costs pursuant to 42 U.S.C. §1988;"
        )
    else:
        items.append("(e) Costs and disbursements of this action;")

    items.append("(f) Such other and further relief as this Court deems just and proper.")

    text = (
        "WHEREFORE, Plaintiff respectfully prays that this Court enter judgment in Plaintiff's "
        "favor and against Defendant(s) and award the following relief:\n\n"
        + "\n\n".join(items)
    )

    return {
        "title": "Prayer for Relief",
        "text": text,
        "includes_1988_fees": has_1983,
        "includes_injunction": ex_parte or seeks_injunction,
    }


# ---------------------------------------------------------------------------
# Missing facts collector
# ---------------------------------------------------------------------------

def _collect_missing_facts(sections: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for section_key, section in sections.items():
        text = section.get("text", "")
        start = 0
        while True:
            idx = text.find("[FACT NEEDED:", start)
            if idx == -1:
                break
            end = text.find("]", idx)
            if end == -1:
                break
            fact = text[idx + len("[FACT NEEDED:"):end].strip()
            if fact not in missing:
                missing.append(fact)
            start = end + 1
    return missing


# ---------------------------------------------------------------------------
# Plain text renderer
# ---------------------------------------------------------------------------

def _render_plain_text(
    plaintiff: Dict[str, str],
    sections: Dict[str, Any],
) -> str:
    divider = "\n" + "=" * 72 + "\n\n"
    parts: List[str] = []
    for key in ["caption", "jurisdiction_venue", "parties", "standing", "facts", "capacity_defendants", "causes_of_action", "prayer"]:
        section = sections.get(key, {})
        if not section:
            continue
        title = section.get("title", key.upper().replace("_", " "))
        parts.append(f"{title.upper()}\n\n{section.get('text', '')}")
    text = divider.join(parts)
    return f"{text}\n\n{divider.strip()}\n\n{DISCLAIMER}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_complaint_draft(
    intake_state: Dict[str, Any],
    complaint_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ComplaintGeneratorServiceError("intake_state must be a dictionary.")

    try:
        results = build_legal_results(intake_state, complaint_id)
    except LegalResultsServiceError as exc:
        raise ComplaintGeneratorServiceError(f"Legal results error: {exc}") from exc

    complaint = _get_complaint_record(intake_state, complaint_id)
    if not complaint:
        raise ComplaintGeneratorServiceError("No complaint record found in intake_state.")

    plaintiff = _get_plaintiff(intake_state)

    para = 1
    caption_section = _build_caption(plaintiff, results)

    jurisdiction_section = _build_jurisdiction_venue(results, para)
    para += jurisdiction_section["paragraph_count"]

    parties_section = _build_parties(plaintiff, complaint, results)
    para += parties_section["paragraph_count"]

    standing_section = _build_standing(results, para)
    para += standing_section["paragraph_count"]

    facts_section = _build_facts(complaint, para)
    para += facts_section["paragraph_count"]

    capacity_section = _build_capacity_defendants(results, complaint, para)
    para += capacity_section["paragraph_count"]

    causes_section = _build_causes_of_action(results, complaint, para)
    para += causes_section["paragraph_count"]

    prayer_section = _build_prayer_for_relief(results, complaint)

    sections = {
        "caption": caption_section,
        "jurisdiction_venue": jurisdiction_section,
        "parties": parties_section,
        "standing": standing_section,
        "facts": facts_section,
        "capacity_defendants": capacity_section,
        "causes_of_action": causes_section,
        "prayer": prayer_section,
    }

    missing_facts = _collect_missing_facts(sections)
    plain_text = _render_plain_text(plaintiff, sections)

    all_case_law = results.get("all_case_law", [])

    return {
        "recommended_court": results.get("jurisdiction", {}).get("recommended_court", "unknown"),
        "overall_strength": results.get("overall_strength", "weak"),
        "complaint_id": complaint.get("complaintId", ""),
        "sections": {k: v.get("text", "") for k, v in sections.items()},
        "sections_meta": {k: {kk: vv for kk, vv in v.items() if kk != "text"} for k, v in sections.items()},
        "plain_text": plain_text,
        "missing_facts": missing_facts,
        "case_law_used": all_case_law,
        "disclaimer": DISCLAIMER,
    }
