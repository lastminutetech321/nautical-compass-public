# Nautical Compass — Execution Engine

## Purpose
Defines how Nautical Compass actually executes the system at runtime.

This is the layer that turns:
- schemas
- specs
- mappings
- routing rules
- output definitions

into working behavior.

---

## Core Role

The execution engine is the translator between:

- intake UI
- stored intake data
- scoring logic
- document generation
- routing logic
- Helm updates
- document history

Without this layer, the specs remain static.

---

## Runtime Chain

```text
User Action
→ UI event
→ intake data write
→ validation
→ score recompute
→ routing recompute
→ document availability update
→ output generation
→ document history append
→ Helm refresh
→ response back to UI
Then verify:

```bash id="aq1lx2"
wc -l docs/product/runtime/execution-engine.md
