# Nautical Compass Frozen Master Update — June 1, 2026

## Current Production URL
LMT321: https://nautical-compass-9rjs6.ondigitalocean.app

## Current Build Status
- Claude/OpenClaw restored through Termius/Tailscale.
- Anthropic/Claude Sonnet 4.6 configured as active model.
- OpenAI Codex OAuth token is broken/expired but no longer blocks workspace.
- Stage 1 Agent Registry completed.
- Stage 1.1 Full 15-agent registry expansion completed.
- Registry loader completed.
- Registry validator completed.
- Public Legal Engine API endpoint display removed from user-facing UI.
- Backend legal API routes remain intact.

## Agent Control Layer Freeze
Agents are registered but remain OFFLINE until capability definitions, permissions, routing, validation, and safe execution are built.

Current registered agents:
- captain_agent
- builder_agent
- validator_agent
- deployment_agent
- monitor_agent
- recovery_agent
- intake_sentinel
- timeline_architect
- evidence_marshal
- accountability_strategist
- standing_analyzer
- capacity_analyzer
- sol_engine
- output_packet_composer
- offer_architecture_agent

Do not turn on 15 autonomous agents at once.
Use controlled workflow only:
Captain -> Builder -> Validator.

## Legal Truth Layer Freeze
Legal agents must remain doctrine-based, evidence-based, and fact-bound.

Core legal flow:
Case Dock -> Intake Sentinel -> Timeline Architect -> Evidence Marshal -> Standing Analyzer -> Capacity Analyzer -> Rights Analysis -> Case Packet -> Complaint Draft.

Standing Analyzer must apply:
- Injury in fact
- Causation
- Redressability
- Lujan v. Defenders of Wildlife, 504 U.S. 555 (1992)
- TransUnion LLC v. Ramirez, 594 U.S. 413 (2021)

Capacity Analyzer must apply:
- Individual capacity
- Official capacity
- Ex parte Young prospective relief
- Kentucky v. Graham, 473 U.S. 159 (1985)
- Monell municipal liability where facts support it
- Qualified immunity screening

## Security Freeze
Public UI must not display raw backend endpoint lists.

Removed from public display:
- POST /api/legal/standing
- POST /api/legal/capacity
- POST /api/legal/rights
- POST /api/legal/regulatory-routes
- POST /api/legal/jurisdiction
- POST /api/legal/results
- POST /api/legal/case-packet
- POST /api/legal/complaint-draft

Backend routes may remain active, but must be validated, rate-limited, and protected before public scale.

## Product Priority Freeze
Next build target is Legal Intake V1, not more architecture.

Priority path:
1. Verify Case Dock saves intake.
2. Verify intake produces structured matter state.
3. Wire Standing Analyzer to intake state.
4. Wire Capacity Analyzer to intake state.
5. Wire Rights Analysis.
6. Assemble Case Packet.
7. Generate Complaint Draft.
8. Add PDF/export later.

## Agent Budget Rule
$127 Claude API credit must be protected.
No autonomous loops.
No 15-agent swarm.
No continuous retry.
No Twilio integration unless intentionally enabled later.

Use controlled tasks:
- Captain = planner/router
- Builder = file/code writer
- Validator = checker/tester

## Growth Layer Freeze
Offer Architecture Agent belongs only in the Growth Layer.
It may optimize:
- offer structure
- pricing ladders
- landing pages
- conversion copy
- value articulation
- retention strategy

It may not alter:
- facts
- evidence
- legal conclusions
- standing analysis
- capacity analysis
- timelines
- remedies
- user rights
- distress-safe rules

Legal Engine = Truth Layer.
Offer Architecture Agent = Packaging Layer.

## Nautical Compass Direction Freeze
NC is a compliance-first, AI-powered business and legal infrastructure platform.
Immediate legal product goal:
A user submits facts through Case Dock and receives structured standing, capacity, rights, evidence, timeline, and case packet output.

Immediate business/product goal:
Move from framework to usable product by completing one end-to-end legal workflow.

## AVPT / Workforce Doctrine Freeze
Preserve progressive data collection:
- never force users to manually enter what AI can extract
- use resume/document extraction
- collect delayed data when knowable
- build confidence scores from objective workflow evidence
- separate reputation categories
- rehire behavior is a primary signal

## Show Orchestration Freeze
Preserve production-flow coordination:
- 72-hour request guidance
- late-request escalation
- PRN/continuity reserve
- department sequencing
- dock congestion modeling
- dependency chains
- live bottleneck tracking
- replacement routing
- timestamped accountability logs

## Community Resource Freeze
Preserve NC as future national assistance and advancement infrastructure:
- modular resource marketplace
- benefits navigation
- workforce/business formation rails
- update/verification system
- future private member marketplace

## Business Formation Rail Freeze
NC should support AV techs, freelancers, contractors, and operators moving from worker to structured operator in DC, Maryland, and Virginia.

Core support:
- entity pathing
- filing sequence
- bank-readiness
- document checklist
- compliance reminders
- renewal tracking
- UCC renewal reminders where applicable
- annual filing review reminders

## Legal Doctrine Expansion Freeze
NC must support harms historically and currently affecting Black people in America, including:
- elder abuse
- deed theft
- child abuse
- discrimination
- sundown-town style exclusion
- institutional retaliation
- provoked police-contact scenarios
- displacement and public-institution capture

Frame by provable conduct, not nationality or immigration status.

## Provoked Police Contact Doctrine
Detect scenarios where a person initiates or escalates contact with a Black person, then frames themselves as victim to trigger police, removal, detention, prosecution, or institutional action.

Document:
- initiation
- escalation
- narrative manipulation
- false fear performance
- resulting state action
- harm
- available remedy paths

## Community Preservation / Institutional Integrity Lane
Analyze:
- land loss
- public contracts
- zoning/redevelopment
- public meeting access
- civil rights discrimination
- employment authorization issues where relevant
- public corruption
- fraud
- unequal treatment
- ultra vires conduct
- de facto officer doctrine
- color-of-law liability
- Monell/custom/failure-to-train where facts support

## Current Immediate Next Build
After this file is committed, continue with:

Legal Intake V1:
- Case Dock save test
- matter state schema
- intake validation
- standing analyzer connection
- capacity analyzer connection
- packet output route

Do not build autonomous agent execution until one legal workflow works end-to-end.
