# Object model: attrs vs. pydantic (revised)

## Status

Supersedes the prototype on `origin/plan-codegen` (`a9b77e8`, "planning",
2026-01-23) — six files (`pydantic_prototype.py`,
`pydantic_prototype_summary.md`, `codegen_comparison.md`,
`codegen_recommendation.md`, `codegen_architecture.py`,
`model_rebuild_explained.md`), never merged. That branch isn't deleted and
its code is still worth mining when this is picked back up (see "What's
still true," below) — but its headline recommendation and effort estimate
are stale as of 2026-09.

## Background

Issue #282 ("Consider switching attrs -> pydantic") gives two motivations:
free JSON Schema, and easier construction/validation mechanics (notably,
validation that can run *after* assignment, which sidesteps friction in
load-time dimension resolution that attrs' init/convert/validate ordering
causes today). The January prototype demonstrated both are technically
achievable and recommended switching flopy4's object model
(`Package`/`Component`) to pydantic during the then-upcoming refactor.

Discussion while writing `docs/dev/netcdf-spec-plan.md` (same architectural
question, applied to the NetCDF I/O object model) produced a sharper
version of the schema argument: JSON Schema is valuable on artifacts meant
for external/cross-tool interop — a file format, a spec other tools
consume — not on an in-memory object model whose only job is ergonomic
construction of a live simulation. That reasoning applies here too, and it
changes the calculus.

## Why the January prototype is stale

### Codebase drift

- **xattree removed** (`67d0922`, 2026-09). The prototype spent real effort
  proving compatibility with the xattree-adjacent parent/dimension-wiring
  design it was written against. That constraint no longer exists — net
  simplification, but it means the prototype's compatibility analysis
  answers a question that no longer applies.
- **`Column`/`Schema` deleted, `Row` unified with `pk`/`fk` metadata**
  (`78c506b`/`6cdfb2a`, 2026-08-19, per `mf6-object-model-plan.md` Phase
  0.6). The prototype's worked examples (DIS/NPF field declarations) are
  ported against the pre-`Row` shape.
- **DFN spec parsing already flipped to pydantic** — `modflow_devtools.dfns`
  dev3, consumed by flopy4's codegen (same `6cdfb2a`, "Phase 0.6a"). The
  prototype predates this and had no visibility into it.
- **Every phase landed since January was built uniformly on
  `attrs.fields()`** as the one field-introspection idiom, by explicit
  design (`mf6-object-model-plan.md` wants exactly one idiom active at a
  time — it says so directly, having just paid down a two-idiom problem for
  `Column`/`Schema` vs. `Row`). Each phase that lands on attrs before a
  pydantic swap happens is more surface area that swap eventually has to
  re-touch. The prototype's "marginal cost, you're already refactoring"
  framing assumed less of this had been built yet.

### Value-conclusion drift

The prototype's headline argument — schema-first design, JSON Schema "for
free" — is now satisfied independently, at the DFN-spec layer in devtools
(Phase 0.6a), without touching `Package`/`Component` at all. Same
conclusion as `netcdf-spec-plan.md`: the schema value lives with the spec
artifact meant for external interop, not with flopy4's in-memory
construction ergonomics.

What's left standing on its own, once the schema argument is subtracted:
`validate_assignment=True` / `model_validator(mode="after")` replacing the
`__attrs_post_init__` super()-chain across `DimensionResolverMixin` →
`Component` → `Package` (`flopy4/dimensions.py`, `flopy4/mf6/component.py`,
`flopy4/mf6/package.py`). Real, still-open friction — but a narrower,
ergonomics-only case, not the two-pronged case the prototype made.

## What's still true from the prototype (worth keeping)

- `Annotated[NDArray[np.float64], ...]` field type hints work fine, dtype-precise.
- `model_validator` + `validate_assignment` does give implicit
  post-assignment validation, which directly addresses the dimension-
  resolution post-init chaining pain.
- Centralizing validation logic in a base-class `model_validator` so
  generated classes reduce to field declarations is still sound in
  principle — though flopy4's codegen has independently converged on thin
  generated classes already via `flopy4/mf6/spec.py`'s `field()` wrapper,
  so this is less of a differentiator than it was in January.
- pydantic is already a proven, unpinned, friction-free dependency in this
  codebase (DFN spec parsing, `flopy4/mf6/netcdf.py`) — the version-pinning
  risk mwtoews flagged on the issue hasn't materialized in practice.

## Revised recommendation

Don't do this now, in parallel with `mf6-object-model-plan.md`'s open
phases. Wait for one of:

1. `mf6-object-model-plan.md` Phase 1 (generalized structuring) lands, so
   there's exactly one field-introspection idiom to migrate off of, not two
   competing ones mid-flight.
2. The `__attrs_post_init__`/`DimensionResolverMixin` chaining becomes an
   active blocker on some other piece of real work (not hypothetical) —
   that would justify pulling this forward ahead of (1).

## Purpose of this branch

Staging ground for updated prototyping once one of the above triggers is
met: port one real, current-shape package (e.g. `Dis` or `Npf`, using
today's `Row`/`pk`/`fk` conventions, no xattree) to pydantic and re-measure
effort/ergonomics against the actual current codebase, rather than trusting
the January estimate (4-5 weeks) at face value — that number was produced
against a codebase materially different from today's.

## Next steps (when picked up)

1. Port one package end-to-end in its current shape.
2. Port its `__attrs_post_init__`/`DimensionResolverMixin` chain; confirm
   `model_validator(mode="after")` actually collapses it the way the
   prototype expected.
3. Re-measure: lines changed, generated-file diff size, whether `Row`/
   `pk`/`fk` metadata conventions transfer cleanly to pydantic's
   `Annotated`/`Field` idiom.
4. Re-decide the full-migration effort estimate and go/no-go from that
   measurement, not from the January prototype's numbers.

## Related

- `docs/dev/netcdf-spec-plan.md` — same schema-value-layering conclusion,
  applied to the NetCDF I/O object model.
- `mf6-object-model-plan.md` — the in-flight refactor this should sequence
  after.
- Issue #282.
- `origin/plan-codegen` (`a9b77e8`) — original prototype code/docs; mine
  `pydantic_prototype.py` for working mechanics when this is picked back
  up, but don't treat its recommendation section as current.
