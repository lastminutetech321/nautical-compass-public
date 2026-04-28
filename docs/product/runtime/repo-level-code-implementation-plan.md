# Nautical Compass — Repo-Level Code Implementation Plan

## Purpose
Maps the first working loop into actual repo-level code structure.

This plan answers:
- where runtime code should live
- what files to create
- what existing files to update
- what functions to build first
- how to connect UI, schema, scoring, generation, and Helm

---

## Current Goal

Build the first real working loop:

1. user fills intake
2. intake data saves
3. scores recompute
4. routes recompute
5. results screen updates
6. user clicks Generate W-9
7. W-9 payload is created
8. review state appears
9. document history updates
10. Helm updates

---

## Repo Strategy

Use the repo in 3 layers:

### Layer 1 — Product Specs
Already created under:
- `docs/product/...`
- `data-model/intake/...`

These remain the source of truth for behavior.

### Layer 2 — Runtime Code
Create real execution code under app code directories.

### Layer 3 — UI Integration
Update templates / frontend handlers so buttons and forms call the runtime code.

---

## Recommended Runtime Folder

Create:

```text
runtime/
runtime/
  intake_state_manager.py
  validation_engine.py
  scoring_executor.py
  routing_executor.py
  prefill_mapper.py
  w9_generator.py
  document_history_logger.py
  helm_state_adapter.py
  execution_orchestrator.py
services/
services/
  intake_service.py
  document_service.py
  helm_service.py
utils/spec_loader.py
Then verify:

```bash id="shp3om"
wc -l docs/product/runtime/repo-level-code-implementation-plan.md
