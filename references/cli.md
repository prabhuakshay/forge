---
name: cli
summary: CLI design and UX conventions
applies_to: ["src/**/cli.py", "src/**/cli/**/*.py", "src/**/__main__.py", "src/**/commands/**/*.py"]
enforcement: blocking
---
# CLI design

Conventions for command-line entrypoints and their command code.

## Structure
- **Subcommands (verb-noun), not a flag-driven monolith.** Group functionality as
  `tool <command> [args]` rather than one command with a thicket of mutually
  exclusive flags.
- Keep the CLI layer thin: parse args, call into the library, format output.
  Business logic lives in importable functions/classes, not in the command body —
  so it's testable without spawning a process.
- One command = one function with a clear signature; the parser wires args to it.

## Arguments & options
- Positional args for the essential subject; options (`--flag`) for modifiers.
- Provide `--help` for every command and subcommand with a real description.
- Sensible defaults; require only what's truly required. Validate early and
  report the *specific* problem.

## Output & exit codes
- Human-readable output to **stdout**; diagnostics, errors, and progress to
  **stderr**. Never mix them.
- Exit `0` on success, non-zero on failure — and use distinct codes for distinct
  failure classes when callers might branch on them.
- Offer a machine-readable mode (`--json`) for anything a script would consume.
- Don't print stack traces to users by default; show a clear message and keep the
  traceback behind `--verbose`/`--debug`.

## Robustness
- Handle `KeyboardInterrupt` cleanly (exit 130, no ugly traceback).
- Make destructive actions confirm (or require `--yes`); never destroy without
  consent.
- Stream large output; don't buffer everything in memory.
