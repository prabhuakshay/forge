"""Stdlib-only support library for the forge plugin.

Everything in this package must run with a bare Python interpreter, BEFORE the
target project's virtualenv exists or its dependencies are installed. Hooks fire
on the very first edit in a fresh checkout, so importing anything third-party
here would crash the workflow at exactly the wrong moment.

The division of labour: this library owns the *plumbing* (state tracking, file
scanning, orchestration) and shells out to the project's own `uv run ...` for the
*tools* (ruff/mypy/pytest), which legitimately live in the project environment.
"""
