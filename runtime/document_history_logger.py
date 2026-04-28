import copy
from typing import Any, Dict, List

from utils.spec_loader import load_spec


class DocumentHistoryError(Exception):
    pass


def _ensure_history_container(intake_state: Dict[str, Any]) -> Dict[str, Any]:
    if "documentProfile" not in intake_state or not isinstance(intake_state["documentProfile"], dict):
        intake_state["documentProfile"] = {}

    if "documentGenerationHistory" not in intake_state["documentProfile"] or not isinstance(
        intake_state["documentProfile"]["documentGenerationHistory"], list
    ):
        intake_state["documentProfile"]["documentGenerationHistory"] = []

    return intake_state


def append_document_record(user_id: str, intake_state: Dict[str, Any], document_record: Dict[str, Any]) -> Dict[str, Any]:
    if not user_id:
        raise DocumentHistoryError("user_id is required.")
    if not isinstance(intake_state, dict):
        raise DocumentHistoryError("intake_state must be a dictionary.")
    if not isinstance(document_record, dict):
        raise DocumentHistoryError("document_record must be a dictionary.")

    state = copy.deepcopy(intake_state)
    state = _ensure_history_container(state)

    history_entry = {
        "documentId": document_record.get("documentId", ""),
        "documentType": document_record.get("documentType", ""),
        "title": document_record.get("title", ""),
        "fileName": document_record.get("fileName", ""),
        "filePath": document_record.get("filePath", ""),
        "createdAt": document_record.get("createdAt", "runtime_generated"),
        "updatedAt": document_record.get("updatedAt", "runtime_generated"),
        "sourceSchema": document_record.get("sourceSchema", "master-intake-schema"),
        "linkedComplaintId": document_record.get("linkedComplaintId", ""),
        "linkedEvidenceIds": document_record.get("linkedEvidenceIds", []),
        "status": document_record.get("status", "generated"),
        "version": document_record.get("version", 1),
        "notes": document_record.get("notes", ""),
        "actor": user_id,
    }

    state["documentProfile"]["documentGenerationHistory"].append(history_entry)
    state["updatedAt"] = "document_history_append"
    return state


def set_document_ready_flag(intake_state: Dict[str, Any], document_type: str) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise DocumentHistoryError("intake_state must be a dictionary.")
    if not document_type:
        raise DocumentHistoryError("document_type is required.")

    state = copy.deepcopy(intake_state)

    if "documentProfile" not in state or not isinstance(state["documentProfile"], dict):
        state["documentProfile"] = {}

    flag_map = {
        "w9": "w9Ready",
        "invoice": "invoiceReady",
        "contractor_profile": "contractorProfileReady",
        "complaint_summary": "complaintSummaryReady",
    }

    flag_key = flag_map.get(document_type)
    if flag_key:
        state["documentProfile"][flag_key] = True

    state["updatedAt"] = "document_ready_flag_set"
    return state


if __name__ == "__main__":
    demo_state = load_spec("master_intake_schema")

    demo_record = {
        "documentId": "doc-w9-001",
        "documentType": "w9",
        "title": "W-9 Draft",
        "fileName": "w9-draft.json",
        "filePath": "/generated/w9-draft.json",
        "status": "generated",
        "notes": "prefill payload generated",
    }

    updated = append_document_record("demo-user", demo_state, demo_record)
    updated = set_document_ready_flag(updated, "w9")

    print("history_count:", len(updated["documentProfile"]["documentGenerationHistory"]))
    print("w9Ready:", updated["documentProfile"].get("w9Ready"))
    print("last_document_type:", updated["documentProfile"]["documentGenerationHistory"][-1]["documentType"])
