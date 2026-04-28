from typing import Any, Dict

from runtime.document_history_logger import append_document_record, set_document_ready_flag
from runtime.helm_state_adapter import build_helm_state
from runtime.intake_state_manager import (
    get_intake_state,
    mark_intake_complete,
    save_intake_section,
    update_intake_field,
)
from runtime.routing_executor import compute_routes
from runtime.scoring_executor import compute_scores
from runtime.validation_engine import validate_section, validate_w9_requirements
from runtime.w9_generator import build_w9_review_state


class ExecutionOrchestratorError(Exception):
    pass


def handle_field_update(
    user_id: str,
    field_path: str,
    value: Any,
    intake_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = intake_state if intake_state is not None else get_intake_state(user_id)
    updated_state = update_intake_field(user_id, field_path, value, state)

    scores = compute_scores(updated_state)
    routes = compute_routes(updated_state, scores)
    history = updated_state.get("documentProfile", {}).get("documentGenerationHistory", [])
    helm_state = build_helm_state(updated_state, scores, routes, history)

    return {
        "event": "field_updated",
        "intakeState": updated_state,
        "scores": scores,
        "routes": routes,
        "helmState": helm_state,
    }


def handle_section_save(
    user_id: str,
    section_id: str,
    payload: Dict[str, Any],
    intake_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = intake_state if intake_state is not None else get_intake_state(user_id)
    updated_state = save_intake_section(user_id, section_id, payload, state)

    validation = validate_section(section_id, updated_state)
    scores = compute_scores(updated_state)
    routes = compute_routes(updated_state, scores)
    history = updated_state.get("documentProfile", {}).get("documentGenerationHistory", [])
    helm_state = build_helm_state(updated_state, scores, routes, history)

    return {
        "event": "section_saved",
        "sectionId": section_id,
        "validation": validation,
        "intakeState": updated_state,
        "scores": scores,
        "routes": routes,
        "helmState": helm_state,
    }


def handle_intake_completion(
    user_id: str,
    intake_state: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ExecutionOrchestratorError("intake_state must be a dictionary.")

    completed_state = mark_intake_complete(user_id, intake_state)
    scores = compute_scores(completed_state)
    routes = compute_routes(completed_state, scores)
    history = completed_state.get("documentProfile", {}).get("documentGenerationHistory", [])
    helm_state = build_helm_state(completed_state, scores, routes, history)

    results_screen = {
        "classificationScore": scores.get("classificationScore"),
        "classificationLabel": scores.get("classificationLabel"),
        "savingsOpportunityScore": scores.get("savingsOpportunityScore"),
        "savingsOpportunityLabel": scores.get("savingsOpportunityLabel"),
        "riskScore": scores.get("riskScore"),
        "riskLabel": scores.get("riskLabel"),
        "complaintStrengthScore": scores.get("complaintStrengthScore"),
        "complaintStrengthLabel": scores.get("complaintStrengthLabel"),
        "recommendedModules": routes.get("recommendedModules", []),
        "priorityActions": routes.get("priorityActions", []),
        "oneClickRoutes": routes.get("oneClickRoutes", {}),
        "generateW9Enabled": validate_w9_requirements(completed_state).get("valid", False),
    }

    return {
        "event": "intake_completed",
        "intakeState": completed_state,
        "scores": scores,
        "routes": routes,
        "helmState": helm_state,
        "resultsScreen": results_screen,
    }


def handle_generate_w9(
    user_id: str,
    intake_state: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(intake_state, dict):
        raise ExecutionOrchestratorError("intake_state must be a dictionary.")

    validation = validate_w9_requirements(intake_state)
    review_state = build_w9_review_state(intake_state)

    updated_state = intake_state
    if review_state.get("valid"):
        document_record = {
            "documentId": "doc-w9-runtime",
            "documentType": "w9",
            "title": "W-9 Draft",
            "fileName": "w9-draft.json",
            "filePath": "/generated/w9-draft.json",
            "status": "generated",
            "notes": "prefill payload generated",
        }
        updated_state = append_document_record(user_id, updated_state, document_record)
        updated_state = set_document_ready_flag(updated_state, "w9")

    scores = compute_scores(updated_state)
    routes = compute_routes(updated_state, scores)
    history = updated_state.get("documentProfile", {}).get("documentGenerationHistory", [])
    helm_state = build_helm_state(updated_state, scores, routes, history)

    return {
        "event": "document_generated",
        "documentType": "w9",
        "validation": validation,
        "reviewState": review_state,
        "intakeState": updated_state,
        "scores": scores,
        "routes": routes,
        "helmState": helm_state,
    }


if __name__ == "__main__":
    demo_user = "demo-user"

    state = get_intake_state(demo_user)

    section_payload = {
        "identityProfile.fullLegalName": "Jane Doe",
        "identityProfile.firstName": "Jane",
        "identityProfile.lastName": "Doe",
        "identityProfile.email": "jane@example.com",
        "identityProfile.phone": "555-123-4567",
        "identityProfile.residentialAddress.street1": "123 Harbor Way",
        "identityProfile.residentialAddress.city": "Baltimore",
        "identityProfile.residentialAddress.state": "MD",
        "identityProfile.residentialAddress.postalCode": "21201",
        "workProfile.workerType": "independent_contractor",
        "incomeProfile.estimatedAnnualGrossIncome": 85000,
        "businessProfile.businessName": "Doe Services",
        "businessProfile.entityType": "none",
        "businessProfile.einAvailable": False,
        "incomeProfile.receives1099": True,
        "workProfile.setsOwnSchedule": True,
        "workProfile.providesOwnTools": True,
        "incomeProfile.hasUnpaidInvoices": True,
        "complaintProfile.hasComplaintOrDispute": True,
    }

    saved = handle_section_save(demo_user, "identity", section_payload, state)
    state = saved["intakeState"]

    completed = handle_intake_completion(demo_user, state)
    state = completed["intakeState"]

    generated = handle_generate_w9(demo_user, state)

    print("results_generateW9Enabled:", completed["resultsScreen"]["generateW9Enabled"])
    print("w9_valid:", generated["reviewState"]["valid"])
    print("w9_status:", generated["reviewState"]["status"])
    print("history_count:", len(generated["intakeState"]["documentProfile"]["documentGenerationHistory"]))
    print("helm_alert:", generated["helmState"]["globalAlertState"])
