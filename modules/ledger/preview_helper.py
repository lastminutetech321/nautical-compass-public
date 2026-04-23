from __future__ import annotations

from typing import Any, Dict

from modules.ledger import (
    EventLedger,
    TransactionLedger,
    CareerDNALedger,
    CompanyRelationLedger,
    ReferralLedger,
)

def get_ledger_preview(limit: int = 10) -> Dict[str, Any]:
    return {
        "event_ledger": EventLedger().tail(limit),
        "transaction_ledger": TransactionLedger().tail(limit),
        "career_dna_ledger": CareerDNALedger().tail(limit),
        "company_relation_ledger": CompanyRelationLedger().tail(limit),
        "referral_ledger": ReferralLedger().tail(limit),
    }

if __name__ == "__main__":
    import json
    print(json.dumps(get_ledger_preview(5), indent=2))
