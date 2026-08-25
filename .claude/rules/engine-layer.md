---
alwaysApply: true
---

# The engine layer

Solverr serves every request through one of two engines, and both of them are derived from an
upstream it still syncs from. This file is the law. The rationale, the measurements behind each
ruling and the sequencing live in
[engine-layer-architecture.md](../../docs/dev/engine-layer-architecture.md); read that before
designing, read this before touching anything.

The goal is **parity and anti-divergence**. Collapsing two implementations into one is the
mechanism rather than the point: the point is that a change to one engine cannot silently miss the
other. Every duplicate is a cost tracked against that.

## What is upstream and what is ours

Solverr has two upstreams and owes both a mergeable diff. The ledger
([upstream-sync.md](../../docs/dev/upstream-sync.md)) tracks each with its own audited-through row.

- **The Chrome clearing core is FlareSolverr's.** Measured 2026-08-25: 166 lines against upstream's
  157, about 30 diverged after normalising naming. It still syncs mechanically.
- **The stealth clearing core is Byparr's.** It shares Byparr's algorithm and its widget constants by
  name and role (`ANCESTOR_DEPTHS`, `MIN_WIDTH`, `MIN_HEIGHT`, `MAX_HEIGHT`, `COOLDOWN`), and the
  ledger's Taken section records four separate ports into it.
- **Everything wrapped around those cores is ours, and it is written twice.** Request-option
  handling, session lifecycle and result assembly are each implemented once per engine. That is
  where the duplication lives, and it is ordinary duplication with no exemption.

**The line runs inside each engine, not between them.** The two cores are two mechanisms, not two
implementations of one rule, so collapsing them would fork both engines from their upstream and buy
nothing.

## Ownership

- **Neither clearing core is taken over.** Both are live sync surfaces. This decline rests on the
  measurements above, so it expires if either diff grows to where the sync tax is already being paid
  anyway. Re-measure before citing it.
- **Neither engine dissolves.** Both keep a live core and lose their wrapper.
- **Adapters are the only seam.** The spine talks to each engine through an adapter, so a renamed
  upstream field breaks one file at import time instead of hiding until a live check.
- **Never reimplement a clearing core in the spine.** A step that starts reimplementing what
  `WebDriverWait` over the challenge selectors does, or what the coordinate click through the closed
  shadow root does, has gone too far.
- **Identity is `SessionRef`**, never a bare session-id string. The two pools can hold the same id,
  which `_cmd_sessions_list` already works around at runtime; a bare string cannot say which engine
  owns a session, so a wrong-pool lookup stays constructible until the type says otherwise.

## The rules that bind every change

- **Write once, both engines get it.** Any change to behaviour a client can observe lands for Chrome
  and stealth in the same commit, not the next one and not a follow-up item. The only exit is a
  named browser-automation mechanism an engine genuinely cannot provide, cited in the commit and
  recorded in the ledger. "The engines are structured differently", "the other side needs a rewrite
  first" and "no caller needs it yet" are not exits, they are the work. If the second half cannot
  ship in the same commit, the change goes back to planning as one item covering both.
- **Sharing the implementation is a means, not the rule.** Declining a code collapse stays allowed
  on cited mechanism grounds (the two clearing cores are the standing example), and it never
  licenses a behaviour fork. Two implementations that must behave identically are pinned by one
  conformance test.
- **Divergent bits are typed capability slots.** Never a nullable field, never a boolean-flag
  combination, never a per-engine branch inside shared code. A capability an engine cannot support
  is routed to one that can, or refused by name. Never a silent no-op: `tabs_till_verify` quietly
  doing nothing on the stealth engine is the defect this rule exists to stop.
- **A shared component either derives a piece of state or does not own it.** Sharing the storage
  while each engine interprets it its own way is a fork wearing shared-code clothing, and nobody
  rules on it because it looks unified.
- **A rule that must hold for both engines exists once**, in this order of preference: a shared
  kernel both call, a typed capability the protocol forces both to answer, or one conformance test
  parameterized over both adapters. A hand-written pair is the last resort and it drifts. The
  conformance rung is `src/test_engine_conformance.py`, driven by `src/engine_fakes.py`; add to it
  rather than writing a second per-engine test, and delete the per-engine test it supersedes.
- **Parity is the default; a gap needs a ruling to stay open.** A gap you notice on a surface you are
  touching is levelled up in that change unless the owner gates it.
- **A decline expires with its evidence.** Record the premise with the decline and treat the decline
  as void once that premise changes.
- **Verify by mutation.** A new test is not done until the production clause it names has been
  deleted, the test seen red, and the clause restored.

## How deep the seam goes, per surface

Every surface sits at a different depth. Assuming one is deeper than it is, is the usual way this
work gets mis-planned.

| Surface | Depth | What is shared | Status |
|---|---|---|---|
| Request boundary | Full takeover | Parsing, typing and validation of every `/v1` parameter | **Done**, `validate_request_types` |
| Result assembly | Full takeover | `assemble` as a pure function of request plus `PageView` | Not started |
| Solve orchestration | Takeover of orchestration | Order of operations, budget, detection, fallback | Not started |
| Challenge clearing | Engine only, by mechanism | Nothing. Declined, see Ownership | Standing decline |
| Sessions | Takeover | One registry keyed by `SessionRef` | Not started |
| Config | Takeover | One environment layer | Not started |
| Passthrough | Not an engine surface | Single implementation already | n/a |

**The two depths fail differently, so look for different things.** A taken-over surface produces
**upstream-drop** bugs: behaviour the replaced code had that ours silently lost. A surface left at
mechanism depth produces **duplicate-implementation** bugs: one rule restated at two sites with one
of them wrong. The cookie-ordering defect found on 2026-08-25 was the second kind. Neither class
shows up in the other's review.

## A takeover is not complete until its behaviour is inventoried

Cutting a surface over and passing `/live-check` is not the completion bar. A live check finds what
you thought to test. A takeover is done when the replaced code's behaviour has been walked end to
end and every item marked **present**, **deliberately dropped** with the reason, or **missing**. The
ledger catches an upstream changing a file after a takeover; nothing else catches what the takeover
failed to carry across in the first place.
