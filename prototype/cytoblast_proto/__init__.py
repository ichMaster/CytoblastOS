"""CytoblastOS v0 prototype.

A thin vertical slice on macOS that tests the product's core hypothesis on live
code before frozen contracts make change expensive. **The integration code of
this package is declared disposable up front** (ROADMAP §v0): what survives into
v1 is the UI, the scenarios, and the findings — never the files.

Consequences, which every module here relies on:

- No abstraction, no contracts, no gate, no store. Platform commands are called
  directly; the OS boundary is laid down in v1.2 from the v0.4 call inventory.
- The invariants in VISION §Principles switch on in v1 — a prototype is exempt
  by design.
- Everything is read-only. The policy gate does not exist until v4, so a write
  path in this package is a scope error.
"""

__all__ = ["__version__"]

__version__ = "0.0.0"
