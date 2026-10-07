# Default Development Environment

Use GitHub Codespaces for PAS builds, tests, dependency installation, and runtime
debugging. Read `docs/cloud-development.zh.md` for the workspace and commands.
The repository is `SissiFeng/paper-attribution-hub`; discover and reuse its existing
Codespace with `gh codespace list` before considering a new instance.

Local source inspection and lightweight edits are fine. Keep large dependencies
and build caches in Codespaces to preserve local disk space. Use a login shell
(`bash -lc`) for remote commands so Codespaces' Git authentication is available.
Check both checkouts for uncommitted work before synchronizing; preserve concurrent
edits and verify the tested commit. Reuse the existing idle-stop configuration.

AWS is the only production deployment target. Codespaces is a development
environment; production data and credentials stay in AWS. Request user sign-in
when authentication expires rather than copying credential caches between hosts.

# 1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

# 2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

# 3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

# 4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
