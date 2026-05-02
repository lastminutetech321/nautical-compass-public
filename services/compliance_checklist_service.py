from typing import Dict, List

CHECKLIST_ITEMS: Dict[str, List[Dict]] = {
    "freelancer": [
        {"id": "ein", "domain": "business_structure", "label": "Obtain EIN from IRS", "required": True},
        {"id": "w9", "domain": "tax", "label": "Complete W-9 on file", "required": True},
        {"id": "quarterly_estimates", "domain": "tax", "label": "Set up quarterly estimated tax payments", "required": True},
        {"id": "bookkeeping", "domain": "tax", "label": "Basic bookkeeping / expense tracking", "required": False},
        {"id": "general_liability", "domain": "insurance", "label": "General liability insurance", "required": False},
        {"id": "client_agreement", "domain": "contracts", "label": "Standard client agreement template", "required": True},
    ],
    "av_tech": [
        {"id": "ein", "domain": "business_structure", "label": "Obtain EIN from IRS", "required": True},
        {"id": "trade_license", "domain": "licensing", "label": "Trade license (local/state)", "required": True},
        {"id": "business_license", "domain": "licensing", "label": "Local business license", "required": True},
        {"id": "w9", "domain": "tax", "label": "Complete W-9 on file", "required": True},
        {"id": "quarterly_estimates", "domain": "tax", "label": "Set up quarterly estimated tax payments", "required": True},
        {"id": "general_liability", "domain": "insurance", "label": "General liability insurance", "required": True},
        {"id": "equipment_insurance", "domain": "insurance", "label": "Equipment / tools insurance", "required": False},
        {"id": "scope_of_work", "domain": "contracts", "label": "Scope-of-work template", "required": True},
    ],
    "sole_proprietor": [
        {"id": "dba", "domain": "business_structure", "label": "DBA (Doing Business As) registration", "required": False},
        {"id": "ein", "domain": "business_structure", "label": "Obtain EIN from IRS", "required": True},
        {"id": "business_license", "domain": "licensing", "label": "Local business license", "required": True},
        {"id": "w9", "domain": "tax", "label": "Complete W-9 on file", "required": True},
        {"id": "quarterly_estimates", "domain": "tax", "label": "Quarterly estimated tax payments", "required": True},
        {"id": "bookkeeping", "domain": "tax", "label": "Bookkeeping / accounting setup", "required": True},
        {"id": "general_liability", "domain": "insurance", "label": "General liability insurance", "required": False},
        {"id": "client_agreement", "domain": "contracts", "label": "Standard client agreement", "required": True},
    ],
    "llc": [
        {"id": "llc_formation", "domain": "business_structure", "label": "LLC formation filed with state", "required": True},
        {"id": "operating_agreement", "domain": "business_structure", "label": "Operating agreement drafted", "required": True},
        {"id": "ein", "domain": "business_structure", "label": "EIN obtained for LLC", "required": True},
        {"id": "business_license", "domain": "licensing", "label": "Local business license", "required": True},
        {"id": "annual_report", "domain": "licensing", "label": "Annual report / renewal filing", "required": True},
        {"id": "bookkeeping", "domain": "tax", "label": "Separate business bank account + bookkeeping", "required": True},
        {"id": "quarterly_estimates", "domain": "tax", "label": "Quarterly estimated tax payments", "required": True},
        {"id": "general_liability", "domain": "insurance", "label": "General liability insurance", "required": True},
        {"id": "client_agreement", "domain": "contracts", "label": "Standard client agreement", "required": True},
    ],
}

DEFAULT_CHECKLIST = CHECKLIST_ITEMS["freelancer"]


def get_checklist_items(operator_type: str) -> List[Dict]:
    return CHECKLIST_ITEMS.get(operator_type, DEFAULT_CHECKLIST)


def score_checklist(responses: Dict[str, bool], operator_type: str) -> Dict:
    items = get_checklist_items(operator_type)
    required = [i for i in items if i["required"]]
    completed = [i for i in required if responses.get(i["id"], False)]
    gaps = [i for i in required if not responses.get(i["id"], False)]

    total = len(required)
    done = len(completed)
    score = round((done / total) * 100) if total else 0

    if score == 100:
        status = "ready"
    elif score >= 60:
        status = "in_progress"
    else:
        status = "not_ready"

    return {
        "score": score,
        "status": status,
        "completed": done,
        "total": total,
        "gaps": gaps,
    }
