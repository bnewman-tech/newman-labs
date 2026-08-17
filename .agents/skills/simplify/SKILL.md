---
name: simplify
description: Run a final behavior-preserving cleanup pass after work is functioning. Use when the user asks to simplify, clean up, de-AI-ize, refactor, remove dead code or helper bloat, reduce technical debt, or review a finished diff across code, tests, configuration, and documentation.
---

# Simplify

Reduce cognitive load after the behavior is understood and working. Ask one
question throughout the pass: what can be deleted, inlined, renamed, or made
more direct without changing the contract?

## Scope

- Start with the requested files or the current diff against the appropriate
  base branch.
- Read the applicable `AGENTS.md` files before judging local patterns.
- Include nearby cleanup only when it is clearly related, low risk, and
  behavior preserving.
- Preserve unrelated user changes in a dirty worktree.
- Avoid broad reorganizations unless the user explicitly requests them.

## Workflow

1. Confirm the current behavior and the checks that establish it.
2. Inspect the diff before editing.
3. Inventory new and changed functions, classes, schemas, tests, configuration,
   and documentation sections.
4. Apply the ownership check to each added abstraction.
5. Search for dead paths, duplicated policy, single-use private helpers,
   pass-through wrappers, stale comments, and speculative fallbacks.
6. Make the smallest high-impact cleanup edits.
7. Re-run targeted checks, then broader checks when the change warrants them.
8. Report what became simpler, why behavior is preserved, and what verification
   passed.

## Ownership check

Keep a boundary when it owns at least one durable responsibility:

- A business rule or policy callers should not duplicate
- External IO, authentication, validation, retry, error, or persistence behavior
- Reused logic substantial enough that inlining creates meaningful duplication
- A readable name for genuinely dense logic
- A framework entrypoint, schema method, or test fixture with a real contract

Inline or delete it when it only:

- Copies or renames fields
- Returns a trivial ID, name, boolean, count, label, or shape
- Wraps one call without adding policy or error behavior
- Exists only as a monkeypatch seam
- Splits obvious top-to-bottom logic into fragments
- Anticipates a future variation that does not exist

## Cleanup priorities

1. Remove dead code, dead branches, unused dependencies, obsolete compatibility
   paths, and stale comments.
2. Inline single-use helpers, constants, wrappers, mappers, and test seams that
   do not own a contract.
3. Collapse duplicated configuration or documentation into one authoritative
   source.
4. Simplify dense branching and naming while preserving ordering and failure
   behavior.
5. Remove generated-looking scaffolding, redundant prose, excessive headings,
   and comments that merely restate the code.
6. Keep tests focused on public behavior and meaningful boundaries instead of
   implementation trivia.

## Preserve

- Public APIs, data shapes, side effects, ordering, and external calls
- Pydantic and static type safety
- Failure sentinels, exception types, retry semantics, and logging contracts
- Trust-boundary checks around external input, authentication, network access,
  persistence, and destructive operations
- Domain-specific helpers whose names make a real policy or protocol clearer

## Do not

- Change behavior just to make the code look cleaner.
- Replace direct code with clever expressions.
- Add `Any`, type ignores, broad exception handling, or silent fallbacks to make
  a cleanup pass easier.
- Extract new helpers unless they own a real boundary or reduce meaningful
  duplication.
- Remove validation, security, or observability that protects a real failure
  mode.
- Call the pass complete if the result is merely different rather than smaller,
  clearer, and easier to maintain.
