# Nautical Compass — Intake UI Layout

## Purpose
Defines the visual layout for the intake experience so the system feels premium, guided, and clear.

The intake should match Nautical Compass:
- cinematic
- controlled
- modular
- not cluttered

---

## Design Principle

The intake is not a boring form stack.

It should feel like:
- entering a guided command system
- moving through stations
- unlocking clarity step by step

---

## Overall Layout

## Desktop
Use a 3-zone layout:

### Zone 1 — Header
Top bar:
- NC mark
- intake title
- progress percentage
- save status
- exit / resume later

### Zone 2 — Main Intake Panel
Center panel:
- current section title
- short explanation
- active fields
- next / back controls

### Zone 3 — Right Insight Rail
Shows:
- live completion %
- current mode
- what this section affects
- locked outputs preview
- quick reassurance text

---

## Mobile / Tablet
Use a stacked layout:

1. Header
2. Progress bar
3. Current section card
4. Fields
5. Sticky next button
6. Expandable insight drawer

Do not force side-by-side on tablet if it feels cramped.

---

## Intake Visual Identity

### Background
Use a softened bridge / helm inspired background, but heavily muted behind the intake card.

The intake must stay readable first.

### Card style
Use:
- glass / frosted panel feel
- subtle border glow
- soft depth
- clean spacing

### Avoid
- too many floating boxes
- bright clutter
- too many simultaneous charts
- over-decorating the form

---

## Screen Flow

## Screen 1 — Welcome / Mode Select
Layout:
- short intro
- “one intake, many outputs”
- mode buttons:
  - General
  - Gig Worker / Contractor
  - Business Owner
  - Legal Issue / Complaint

CTA:
- Start Intake

---

## Screen 2 — Identity
Layout:
- simple personal info block
- 2-column desktop
- 1-column mobile

Right rail:
- “Used for documents, profile, and routing”

---

## Screen 3 — Address
Layout:
- compact address grid
- country defaulted
- minimal friction

Right rail:
- “Used for forms and service area logic”

---

## Screen 4 — Work Classification
Layout:
- choice cards + short yes/no questions
- platform tags
- worker-type guidance text

Right rail:
- “This affects classification and routing”

---

## Screen 5 — Income Profile
Layout:
- income inputs
- slider or number fields
- gross / net side by side on desktop

Right rail:
- “This affects savings and opportunity scoring”

---

## Screen 6 — Expense Profile
Layout:
- toggle groups
- business use questions
- vehicle and tools grouped visually

Right rail:
- “This affects savings and deductions logic”

---

## Screen 7 — Business Structure
Layout:
- operating capacity cards
- EIN yes/no
- business bank account yes/no
- business name field appears conditionally

Right rail:
- “This affects risk and entity readiness”

---

## Screen 8 — Compliance
Layout:
- yes/no checklist
- contracts
- invoices
- taxes
- insurance

Right rail:
- “This affects risk score and protection routing”

---

## Screen 9 — Complaint Intake (Optional)
Layout:
- show only if user selects issue flow
- large narrative box
- category selector
- money loss field
- target party field

Right rail:
- “This can generate a curated complaint summary”

---

## Screen 10 — Evidence Upload (Optional)
Layout:
- upload zone
- file list
- simple labels
- note field

Right rail:
- “Evidence strengthens complaint and escalation paths”

---

## Screen 11 — Goals
Layout:
- goal cards
- multi-select
- short explanatory line under each

Options:
- reduce taxes
- get paid
- structure business
- file complaint
- scale income
- protect assets

Right rail:
- “These goals influence recommended modules”

---

## Screen 12 — Results / Next Steps
Layout:
Main result card shows:
- likely classification
- savings opportunity
- risk level
- complaint strength if applicable
- recommended modules

Buttons:
- Generate W-9
- Generate Invoice
- Build Complaint Summary
- Open Contractor Profile
- Upgrade Now

Right rail:
- “Take the Helm”
- mini output summary

---

## Navigation Rules

### Persistent controls
- Back
- Next
- Save and resume later

### Progress display
Show:
- section count
- percentage
- completed steps

### Validation behavior
- only block on required fields
- optional sections must remain skippable
- explain why a blocked field matters

---

## Microcopy Rules

Tone:
- direct
- calm
- premium
- confident

Examples:
- “Let’s position your system clearly.”
- “This helps us reduce confusion later.”
- “You can skip this for now.”
- “This section strengthens your outputs.”

Avoid:
- robotic legalese
- overly cute consumer copy
- fear-heavy warnings

---

## Interaction Behavior

### Field interactions
- smooth focus states
- clear active field glow
- no aggressive animation

### Section transitions
- slide/fade
- quick and controlled
- no flashy motion

### Auto-save
- save after every major change
- show “Saved” quietly in header

---

## Results Screen Design Rule

The result screen should feel like:
- a command summary
- not a quiz result
- not a generic dashboard

It should answer:
- where user stands
- what is exposed
- what can be generated now
- what path should be opened next

---

## Helm Connection

After intake completion:
- user enters Helm with live values
- gauges reflect risk, opportunity, and direction
- result screen acts as bridge between intake and Helm

---

## Final UI Rule

The intake should feel like entering Nautical Compass through a guided hall, not filling out paperwork.

Clarity first.
Motion second.
Style third.
