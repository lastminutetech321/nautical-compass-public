# CLAUDE OPERATOR RAIL DIRECTIVE

Project: Nautical Compass / JurisEngine / AV Plus Trades
Branch: overnight-operator-rail-batch

Framework correction:
This app is FastAPI + Jinja2, not Flask.
Do not use Flask.
Do not create Flask Blueprints.
Do not import flask.
Use FastAPI APIRouter patterns.

Hard rules:
- Do not rebuild from scratch.
- Do not overwrite main.py wholesale.
- Do not touch payments, Stripe, secrets, .env, production database, or schema migrations.
- Preserve working routes.
- Work in small commits.
- If blocked, skip and continue.
- Do not merge.
- Do not deploy.

Primary goal:
Build Nautical Compass as a compliance-first Operator Rail platform that helps workers, AV techs, freelancers, contractors, and early operators move from worker status into structured operator status.

Start with Phase 1 only.

PHASE 1 — FOUNDATION REGISTRY ONLY

Create or update only these files:
- docs/module_registry.md
- docs/operator_rail_architecture.md
- docs/route_map.md
- agent_logs/operator_rail_batch_summary.md

Do not touch in Phase 1:
- main.py
- existing routes
- payments
- Stripe
- .env
- database schema
- templates
- services

Module families to document:
A. Operator Rail Core
B. Legal / Standing / Capacity
C. AV Plus Trades
D. Financial / Payment / Tax Readiness
E. Compliance / Renewal / Filing
F. Public Growth / Access
G. Admin / Audit / Automation

After Phase 1:
Stop and summarize before adding routes, templates, or services.
