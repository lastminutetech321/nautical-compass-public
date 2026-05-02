# Nautical Compass Agent Runbook

## Core Rule
Termius is for shell commands only. AI/task instructions go in AGENT_TASKS files, not directly into the terminal.

## Environment Separation
- Termius: git, cd, nano, python, grep, curl, deploy checks.
- Agent/AI: read task files, edit repo files, summarize changes.
- Never paste English build directives directly into the shell.

## Branch Rules
1. Always check branch:
   git branch --show-current
2. Never edit directly on main unless doing an emergency hotfix.
3. Feature branches must be named clearly.
4. Push feature branch first.
5. Merge to main only after compile gate passes.

## Safety Rules
- Do not rewrite main.py wholesale.
- Do not touch .env secrets.
- Do not change Stripe keys.
- Do not delete working routes.
- Do not run eval loops on task files.
- Do not execute AGENT_TASKS/*.md as shell scripts.

## Required Gates
Before merge:
1. python3 scripts/agent_compile_gate.py
2. python3 scripts/agent_route_audit.py
3. python3 scripts/agent_deploy_report.py

## Recovery Priority
1. Restore visible service ports/buttons.
2. Fix Command Deck motion: water, vessel, wheel.
3. Fix sound toggle and browser audio permission flow.
4. Check Stripe env vars + checkout routes + DigitalOcean runtime logs.
5. Verify gauges API endpoints and reconnect UI.
6. Wire deeper end-to-end service flow only after recovery is stable.
