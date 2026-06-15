# Aperture — Methods Registry (recursive, agent-auditable)

> State: live · Optionality: HIGH · Open to Change: yes, recursively. History is append-only and solid (it happened); methods/targets are open.
> Purpose: the single place where **verified working methods** are recorded as we discover them, so Mika's AI agents can audit, challenge, and improve them toward the high-level outcomes — without re-deriving from scratch each session.

## Why this exists

Per Mika (2026-06-15): *"as we work and working methods are discovered, log it all and keep the git repo continuously up to speed — camera connectivity, reliably-measured weight accuracy, ML/RL continuity — all recursive for my AI agents to change as audits and reasoning sweeps are conducted."*

This registry is the **execution-layer memory** for that loop. It mirrors the Null Systems engineering bar's pillar 5 (audit-replayable decisions) and the existing recursive docs (`docs/ACCURACY-ROADMAP.md`, `docs/LEARNING-LOOPS.md`).

## The three domains

| Domain | File | What it tracks |
|---|---|---|
| Camera connectivity | [`camera-connectivity.md`](camera-connectivity.md) | How we get a live frame from the Cul2vate camera — verified path, current blocker, one-shot unblock |
| Weight accuracy | [`weight-accuracy.md`](weight-accuracy.md) | Measured accuracy + the method portfolio that moves it (links `ACCURACY-ROADMAP.md`) |
| ML / RL continuity | [`ml-rl-continuity.md`](ml-rl-continuity.md) | The learning loop: what's real vs stub, cadence, safeguards (links `LEARNING-LOOPS.md`) |

Cross-cutting append-only journal: [`SESSION-LOG.md`](SESSION-LOG.md).

## The recursion protocol (how agents use this)

Every method file carries the same shape:

1. **Verified working method** — only methods *first-hand observed to work*. Confidence-tag everything: `[VERIFIED]` / `[LIKELY]` / `[UNVERIFIED]`. No method graduates from "candidate" to "verified" without a first-hand observation logged in the change-log.
2. **Current status / blocker** — what's true right now, and what's stopping the next step.
3. **Candidate improvements / open questions** — the backlog the recursion draws from.
4. **Change-log** — dated, append-only. Each entry: what changed, the evidence, the confidence, and (for reversible changes) how to roll back.

**Before** an agent changes a method: read its file. **After** verifying a change: append a change-log entry **and** commit (`docs: methods/<domain> — <what changed>`). Never rewrite history — supersede it (mark the old entry, add the new). The git history is the audit trail; keep it continuously current.

## Anti-patterns (do not let these happen)

- Marking a method `[VERIFIED]` from a plan or a self-report instead of a first-hand run. (The repo already had two of these: a "sent" email that was a draft, and "extracted" historical data that was an empty folder — caught 2026-06-15. Verify against primary sources.)
- Editing a method silently with no change-log entry → breaks auditability.
- Fabricating data/results to "fill a gap" (per `feedback_real_data_not_synthetic`). A blank is honest; a fake is poison.
- Letting git drift behind the working state. Commit as methods are discovered.
