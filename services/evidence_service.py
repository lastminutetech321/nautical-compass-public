from typing import Any, Dict, List, Optional


class EvidenceServiceError(Exception):
    pass


# ---------------------------------------------------------------------------
# Complaint-draft evidence analysis
# ---------------------------------------------------------------------------

_DOCUMENTARY_TYPES = {"document", "invoice", "contract", "record", "report", "letter", "form", "filing"}
_DIGITAL_TYPES = {"screenshot", "photo", "image", "log", "email", "attachment", "video", "recording", "audio"}
_WITNESS_TYPES = {"witness", "declaration", "affidavit", "statement", "testimony"}
_COMMUNICATIONS_TYPES = {"sms", "text", "call", "voicemail", "chat", "message", "correspondence"}


def _classify_item(item: Dict[str, Any]) -> str:
    raw_type = (item.get("type", "") or "").lower()
    label = (item.get("label", "") or "").lower()
    tags = [t.lower() for t in (item.get("tags", []) or [])]
    combined = f"{raw_type} {label} {' '.join(tags)}"

    if any(t in combined for t in _WITNESS_TYPES):
        return "witness"
    if any(t in combined for t in _COMMUNICATIONS_TYPES):
        return "communications"
    if any(t in combined for t in _DIGITAL_TYPES):
        return "digital"
    if any(t in combined for t in _DOCUMENTARY_TYPES):
        return "documentary"
    return "other"


def analyze_evidence_for_complaint(
    intake_state: Dict[str, Any],
    complaint_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Categorize evidenceProfile items and flag missing critical evidence types.
    Categories: documentary, digital, witness, communications, other.
    """
    if not isinstance(intake_state, dict):
        raise EvidenceServiceError("intake_state must be a dictionary.")

    evidence_profile = intake_state.get("evidenceProfile", {}) or {}
    items = evidence_profile.get("evidenceItems", []) or []

    complaints = intake_state.get("complaintProfile", {}).get("complaints", []) or []
    complaint: Dict[str, Any] = {}
    if complaint_id:
        complaint = next((c for c in complaints if c.get("complaintId") == complaint_id), {})
    elif complaints:
        complaint = complaints[0]

    text = " ".join([
        complaint.get("category", ""),
        complaint.get("whatHappened", ""),
        complaint.get("plainLanguageSummary", ""),
    ]).lower()

    # Filter to items linked to this complaint when possible
    if complaint_id:
        linked = [i for i in items if complaint_id in (i.get("linkedComplaintIds") or [])]
        if not linked:
            linked = items
    else:
        linked = items

    categorized: Dict[str, List[Dict[str, Any]]] = {
        "documentary": [],
        "digital": [],
        "witness": [],
        "communications": [],
        "other": [],
    }
    for item in linked:
        cat = _classify_item(item)
        categorized[cat].append(item)

    # Missing evidence flags
    missing_flags: List[str] = []

    if any(t in text for t in ["account", "cp&i", "billing", "record", "service", "cutoff"]):
        has_account = any(
            any(t in (i.get("label", "") or "").lower() for t in ["account", "cp&i", "billing", "record"])
            for i in linked
        )
        if not has_account:
            missing_flags.append("[FACT NEEDED: CP&I records and account timeline — subpoena or request from defendant]")

    if any(t in text for t in ["email", "text", "sms", "message", "communication", "phone"]):
        has_comms = bool(categorized["communications"])
        if not has_comms:
            missing_flags.append("[FACT NEEDED: communication records — screenshots, SMS/call logs, or email thread]")

    if any(t in text for t in ["screenshot", "screen", "digital", "online", "website", "portal"]):
        has_digital = bool(categorized["digital"])
        if not has_digital:
            missing_flags.append("[FACT NEEDED: digital/screenshot evidence — capture portal or app screens showing the issue]")

    injury_claimed = bool(complaint.get("injuryClaimed"))
    if injury_claimed:
        has_medical = any(
            any(t in (i.get("label", "") or "").lower() for t in ["medical", "hospital", "doctor", "treatment", "injury"])
            for i in linked
        )
        if not has_medical:
            missing_flags.append("[FACT NEEDED: medical records / treatment documentation — attach all bills and clinical notes]")

    has_any_evidence = bool(linked)
    if not has_any_evidence:
        missing_flags.append("[FACT NEEDED: no evidence items on file — gather all relevant documents, records, and communications]")

    strength: str
    if has_any_evidence and not missing_flags:
        strength = "strong"
    elif has_any_evidence:
        strength = "moderate"
    else:
        strength = "weak"

    return {
        "complaintId": complaint.get("complaintId", ""),
        "total_items": len(linked),
        "categorized": {k: [i.get("label", i.get("evidenceId", "")) for i in v] for k, v in categorized.items()},
        "categorized_items": categorized,
        "missing_flags": missing_flags,
        "strength": strength,
        "note": "Evidence categorized from intake profile. Missing flags indicate items to gather before filing.",
    }


def _safe_bool(value: Any) -> bool:
    return bool(value)


def get_evidence_summary(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise EvidenceServiceError("intake_state must be a dictionary.")

    evidence_profile = intake_state.get("evidenceProfile", {}) or {}
    evidence_items = evidence_profile.get("evidenceItems", []) or []

    return {
        "hasEvidence": _safe_bool(evidence_profile.get("hasEvidence")) or len(evidence_items) > 0,
        "evidenceCount": len(evidence_items),
        "items": evidence_items,
    }


def add_evidence_item(
    intake_state: Dict[str, Any],
    evidence_item: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise EvidenceServiceError("intake_state must be a dictionary.")
    if not isinstance(evidence_item, dict):
        raise EvidenceServiceError("evidence_item must be a dictionary.")

    state = dict(intake_state)
    state.setdefault("evidenceProfile", {})
    state["evidenceProfile"].setdefault("evidenceItems", [])

    item = {
        "evidenceId": evidence_item.get("evidenceId", f"ev-{len(state['evidenceProfile']['evidenceItems']) + 1}"),
        "label": evidence_item.get("label", ""),
        "type": evidence_item.get("type", "unknown"),
        "description": evidence_item.get("description", ""),
        "source": evidence_item.get("source", ""),
        "fileName": evidence_item.get("fileName", ""),
        "filePath": evidence_item.get("filePath", ""),
        "date": evidence_item.get("date", ""),
        "linkedComplaintIds": evidence_item.get("linkedComplaintIds", []),
        "tags": evidence_item.get("tags", []),
    }

    state["evidenceProfile"]["evidenceItems"].append(item)
    state["evidenceProfile"]["hasEvidence"] = True
    return state


def link_evidence_to_complaint(
    intake_state: Dict[str, Any],
    complaint_id: str,
    evidence_id: str,
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise EvidenceServiceError("intake_state must be a dictionary.")
    if not complaint_id:
        raise EvidenceServiceError("complaint_id is required.")
    if not evidence_id:
        raise EvidenceServiceError("evidence_id is required.")

    state = dict(intake_state)

    complaint_profile = state.setdefault("complaintProfile", {})
    complaints = complaint_profile.setdefault("complaints", [])

    evidence_profile = state.setdefault("evidenceProfile", {})
    evidence_items = evidence_profile.setdefault("evidenceItems", [])

    complaint_found = False
    for complaint in complaints:
        if complaint.get("complaintId") == complaint_id:
            complaint.setdefault("relatedEvidenceIds", [])
            if evidence_id not in complaint["relatedEvidenceIds"]:
                complaint["relatedEvidenceIds"].append(evidence_id)
            complaint_found = True
            break

    if not complaint_found:
        raise EvidenceServiceError(f"Complaint not found: {complaint_id}")

    evidence_found = False
    for evidence in evidence_items:
        if evidence.get("evidenceId") == evidence_id:
            evidence.setdefault("linkedComplaintIds", [])
            if complaint_id not in evidence["linkedComplaintIds"]:
                evidence["linkedComplaintIds"].append(complaint_id)
            evidence_found = True
            break

    if not evidence_found:
        raise EvidenceServiceError(f"Evidence not found: {evidence_id}")

    return state


if __name__ == "__main__":
    demo_state = {
        "complaintProfile": {
            "complaints": [
                {
                    "complaintId": "complaint-1",
                    "relatedEvidenceIds": [],
                }
            ]
        },
        "evidenceProfile": {
            "hasEvidence": False,
            "evidenceItems": [],
        },
    }

    demo_state = add_evidence_item(
        demo_state,
        {
            "evidenceId": "ev-1",
            "label": "Invoice PDF",
            "type": "document",
            "description": "Invoice showing unpaid balance",
            "source": "user_upload",
            "fileName": "invoice.pdf",
            "filePath": "/uploads/invoice.pdf",
            "date": "2026-03-29",
            "tags": ["invoice", "payment"],
        },
    )

    demo_state = link_evidence_to_complaint(demo_state, "complaint-1", "ev-1")
    summary = get_evidence_summary(demo_state)

    print("hasEvidence:", summary["hasEvidence"])
    print("evidenceCount:", summary["evidenceCount"])
    print("firstEvidenceId:", summary["items"][0]["evidenceId"])
    print("linkedComplaintIds:", summary["items"][0]["linkedComplaintIds"])
