# Nautical Compass — W-9 Output Flow

## Purpose
Defines the first working output loop for Nautical Compass:

Intake → schema → prefill mapping → W-9 payload → review state

This is the first real generation path and proves the system can turn intake data into a usable output.

---

## Flow Summary

1. User completes intake
2. System stores data in `master-intake-schema.json`
3. System applies `prefill-mapping-spec.json`
4. System applies `w9-generator-spec.json`
5. System validates required fields
6. System builds a W-9 payload
7. User reviews payload before export
8. System marks W-9 as generated in document history

---

## Required Files

### Source files
- `data-model/intake/master-intake-schema.json`
- `data-model/intake/prefill-mapping-spec.json`
- `data-model/intake/w9-generator-spec.json`

### Output support
- `data-model/intake/evidence-vault-spec.json`
- `data-model/intake/upgrade-routing-spec.json`

---

## Trigger Points

The W-9 flow can start from:

- intake results screen
- document actions panel
- contractor profile area
- Helm recommended action
- one-click document generation button

Primary CTA label:
**Generate W-9**

---

## Generation Conditions

The system should allow generation only if these fields exist:

- `identityProfile.fullLegalName`
- `identityProfile.residentialAddress.street1`
- `identityProfile.residentialAddress.city`
- `identityProfile.residentialAddress.state`
- `identityProfile.residentialAddress.postalCode`

If any required field is missing:
- block output
- show missing field list
- route user back to exact intake section

---

## Mapping Logic

### Name line
Use:
- `identityProfile.fullLegalName`

### Business name line
Use:
- `businessProfile.businessName`
If blank:
- leave blank

### Tax classification
Resolve from:
- `businessProfile.entityType`

Fallback:
- `individual_sole_proprietor`

### Address
Use:
- street1
- city
- state
- postalCode

### TIN type
Resolve from:
- `businessProfile.einAvailable`

If true:
- EIN

If false:
- SSN or individual TIN

Do not auto-fill TIN value unless user has explicitly approved secure use.

---

## Output Object

The generated payload should look like:

```json id="iz60ro"
{
  "documentType": "w9",
  "status": "prefilled",
  "reviewRequired": true,
  "payload": {
    "nameLine": "",
    "businessNameLine": "",
    "federalTaxClassification": "",
    "addressLine1": "",
    "city": "",
    "state": "",
    "zip": "",
    "tinType": "",
    "tinValue": ""
  }
}
Then verify:

```bash id="1z7w9u"
wc -l docs/product/output/w9-output-flow.md
