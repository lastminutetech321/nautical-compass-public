# Nautical Compass — Intake Form Specification

## Purpose
Defines the actual user-facing intake experience.

This intake feeds:
- classification
- scoring
- document generation
- complaint curation
- upgrade routing
- Helm system state

This is the **single entry point** into Nautical Compass.

---

## Core Principle

One intake.
Everything downstream is generated.

---

## Intake Modes

User selects entry mode:

- General (default)
- Gig Worker / Contractor
- Business Owner
- Legal Issue / Complaint

Mode adjusts visible questions but still writes to the same schema.

---

## Section 1 — Identity

Fields:
- Full Legal Name
- First Name
- Last Name
- Date of Birth
- Phone
- Email

---

## Section 2 — Address

Fields:
- Street
- City
- State
- ZIP
- Country

---

## Section 3 — Work Classification

Fields:
- Do you receive 1099 income? (yes/no)
- Do you receive W-2 income? (yes/no)
- Platforms worked (Uber, Lyft, Instacart, AV, etc.)
- Do you set your own schedule? (yes/no)
- Do you provide your own tools or vehicle? (yes/no)
- Average weekly hours

---

## Section 4 — Income Profile

Fields:
- Estimated annual gross income
- Estimated net income
- Any unpaid invoices? (yes/no)
- Primary income type:
  - hourly
  - per job
  - contract
  - mixed

---

## Section 5 — Expense Profile

Fields:
- Do you use a vehicle for work? (yes/no)
- Do you track mileage? (yes/no)
- Estimated annual business expenses
- Equipment/tools owned

---

## Section 6 — Business Structure

Fields:
- Operating as:
  - individual
  - LLC
  - corporation
- EIN available? (yes/no)
- Separate business bank account? (yes/no)
- Business name (if any)

---

## Section 7 — Compliance Awareness

Fields:
- Do you use written contracts? (yes/no)
- Do you issue invoices? (yes/no)
- Have you filed business taxes properly? (yes/no/unsure)

---

## Section 8 — Complaint Intake (Optional)

Trigger: user selects “I have an issue”

Fields:
- Who is the issue with?
- What happened? (free text)
- Category:
  - payment issue
  - deactivation
  - contract dispute
  - workplace issue
  - other
- Date(s)
- Location
- Estimated financial loss
- Desired outcome

---

## Section 9 — Evidence Upload (Optional)

Fields:
- Upload files
- Upload screenshots
- Upload contracts
- Upload communication logs

---

## Section 10 — Goals

Fields:
- What do you want help with?
  - reduce taxes
  - get paid
  - structure business
  - file complaint
  - scale income
  - protect assets

---

## Completion Behavior

System generates automatically:

- classification profile
- savings opportunity score
- risk score
- complaint strength score
- recommended modules
- upgrade paths
- prefilled documents:
  - W-9
  - invoice
  - complaint summary
  - contractor profile

---

## UX Rules

- do not overwhelm user
- progressive reveal (sections unlock step by step)
- auto-save every input
- show completion % live
- allow skip on non-critical sections
- allow resume later

---

## Helm Integration

After submission:

Helm updates to show:

- system state
- exposure level
- next action
- recommended path

---

## Output Guarantee

Every completed intake must produce:

- usable profile
- at least 1 recommended action
- at least 1 upgrade path (if applicable)

No dead ends.

---

## Final Rule

The intake is not a form.

The intake is the **entry into the system**.
