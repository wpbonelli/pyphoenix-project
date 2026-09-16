# Object model: attrs vs. pydantic (revised)

## Status

Supersedes the prototype on `origin/plan-codegen` (`a9b77e8`, "planning",
2026-01-23) — six files (`pydantic_prototype.py`,
`pydantic_prototype_summary.md`, `codegen_comparison.md`,
`codegen_recommendation.md`, `codegen_architecture.py`,
`model_rebuild_explained.md`), never merged. That branch isn't deleted and
its code is still worth mining when this is picked back up (see "What's
still true," below) — but its headline recommendation is stale as of
2026-09.

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
ergonomics against the actual current codebase, rather than trusting the
January prototype's conclusions at face value — those were produced against
a codebase materially different from today's.

## Prototype results (2026-09-16)

Steps 1-2 below are done: `docs/dev/prototypes/pydantic_dis_prototype.py`
ports `Dis` (via `DisBase`/`Package`/`Component`/`DimensionResolverMixin`,
`flopy4/mf6/gwf/{dis,disbase}.py`, `flopy4/mf6/{package,component}.py`,
`flopy4/dimensions.py`) to pydantic in its current, post-`Row` shape, and
runs (`pixi run -e dev python docs/dev/prototypes/pydantic_dis_prototype.py`)
against real assertions: derived dims (`nodes`/`ncpl`/`nvert`) compute
correctly, griddata scalar defaults broadcast to full arrays, a child
component (`ncf`, stubbed) gets parent-wired, and `validate_assignment=True`
catches a bad post-construction assignment. It is a scoped-down measurement,
not a drop-in replacement — see "Explicitly out of scope" below.

**What ported cleanly, lower cost than expected:**

- Parent/child wiring is *simpler* in pydantic than attrs, not just
  equivalent: attrs needs a private-attribute naming convention (`_parent`
  field, `parent=` constructor kwarg, via leading-underscore mangling) to
  get a public-looking accessor; pydantic just names the field `parent`
  directly (`Field(exclude=True)` keeps it out of `model_dump()`/schema).
  No trick needed.
- `attrs.fields(cls)` → `cls.model_fields`, `.metadata` dict →
  `Field(json_schema_extra={...})`: a direct, mechanical swap, field by
  field. Every place `spec.py`'s `field()` helper writes to `metadata[...]`
  has an equally-simple pydantic equivalent.
- `model_post_init` not auto-chaining across the MRO (each override must
  call `super().model_post_init(context)` itself) turned out to be a wash,
  not a new cost — attrs' `__attrs_post_init__` already required the same
  explicit `super()` chaining discipline.
- `validate_assignment=True` delivers the concrete ergonomics win issue
  #282 actually asked for: a later bad assignment (`dis.xorigin = "not a
  float"`) is now caught automatically. Confirmed working in the demo.
- Array-field coercion (below) also turned out to be a one-time cost, not a
  per-field one — see the correction under "What's real."

**What's real (a genuine, newly-surfaced correctness gap, but a one-time
fix, not a per-field one):**

- Pydantic strictly validates `NDArray`-typed fields: constructing
  `DisProto(delr=100.0, ...)` — the exact call shape `Dis(delr=100.0, ...)`
  uses today, a bare scalar against an array-typed field — raised
  `ValidationError: Input should be an instance of ndarray`. attrs never
  validates this (no validator attached to the field by default), so the
  scalar-default-for-an-array-typed-field pattern (used throughout
  DIS/DISV/NPF/IC/STO/... griddata fields) just works there today.
  An earlier revision of this prototype fixed this with a `field_validator`
  declared per array field on `DisProto` and described it as an unavoidable
  per-generated-field cost. **That was wrong, and worth flagging as a
  correction rather than quietly fixing:** a single `field_validator("*",
  mode="before")`, defined once on the shared `PackageBase`, driven by each
  field's own `json_schema_extra["shape"]` metadata (the same metadata
  `flopy4/mf6/spec.py`'s `field()` helper already emits today), covers
  every array field on every subclass — present and future — including
  under `validate_assignment=True` (`d.delr = 5.0` after construction still
  coerces correctly, confirmed with a standalone test). Codegen doesn't
  need to emit anything new for this; the `shape=` metadata it already
  writes is sufficient.
- `attrs.field(init=False)` (`DisBase`'s derived `nlay`/`nrow`/`ncol`/
  `ncpl`/`nvert`/`nodes` — computed, never user-supplied) has no `BaseModel`
  equivalent (that's a `pydantic.dataclasses.dataclass` feature). The
  prototype falls back to "normal field, unconditionally overwritten in
  `model_post_init`" — which means a caller *can* pass `nodes=` at
  construction and have it silently discarded, where attrs raises
  `TypeError: unexpected keyword argument`. A real behavioral regression if
  this ships as-is; fixable (reject the key explicitly in a `mode="before"`
  validator) but is more code than attrs needed for the same guarantee.
- `attrs.Factory(lambda self: ..., takes_self=True)` (`Component.name`'s
  default: the lowercased *runtime* class name) also has no direct
  `Field(default_factory=...)` equivalent (those callables take no
  arguments) — replaced with a `model_validator(mode="after")`. Composes
  fine, but it's one more method where attrs needed a one-line `Factory`.

**Explicitly out of scope for this measurement (deferred, not glossed
over)** — each of these is real remaining migration surface, not yet
priced:

- `Component`'s full `MutableMapping` interface (`__getitem__`/
  `__setitem__`/`__delitem__`, list/dict child collections) — `Dis` only
  exercises the single-child ("only") case via `ncf`.
- `Package`'s Item-list period-data coercion (`_init_item_lists`,
  `construct_item`/`construct_union_item`) — `Dis` has no period block, so
  this path is entirely untouched here. `Npf` (the plan's other suggested
  candidate) wouldn't exercise it either; a list-heavy package (`Wel`,
  `Chd`, ...) would be needed to measure this.
- Every consumer that reads `attrs.fields()`/`.metadata` off a live
  `Package` today. Measured directly (not estimated): ~50 call sites across
  12 files (`component.py`, `package.py`, `dimensions.py`, `spec.py`,
  `item.py`, `record.py`, `adapters.py`, `attrs_xarray.py`, `netcdf.py`,
  `converter/ingress/structure.py`, `converter/egress/unstructure.py`,
  `gwf/disbase.py`), concentrated most heavily in
  `converter/ingress/structure.py` and `netcdf.py`. Each individual call
  site is the same mechanical swap this prototype already demonstrates
  (`attrs.fields(cls)` → `cls.model_fields`, `attr.metadata.get(...)` →
  `finfo.json_schema_extra.get(...)`) — no single one is hard. The cost is
  the count: ~50 independent edit sites is real surface area to touch and
  re-test, and dominates total migration size far more than porting any
  individual leaf package's field declarations does. Not measured here:
  whether `attrs.Attribute.type` and pydantic's `FieldInfo.annotation`
  ever disagree on a case this prototype didn't exercise (e.g. how each
  represents `Optional`/`Union` for a field type) — worth checking against
  the two largest files above before trusting the swap is mechanical
  everywhere.

## Re-assessed recommendation

The measurement doesn't change the "wait for a trigger" recommendation
above. It does relocate where the real cost lives: not in per-field
boilerplate (the array-coercion validator collapses to one reusable
definition, not one per field or per package), but in (a) faithfully
porting `Component`/`Package`/`DimensionResolverMixin` themselves — the
`MutableMapping` interface and Item-list coercion are still unmeasured —
and (b) the ~50-call-site consumer surface outside the object model itself
(`netcdf.py`, `converter/*`, `codec/*`). Both are one-time, codebase-wide
costs rather than a cost that scales with how many packages get migrated.

## Next steps (when picked up for a real migration decision)

1. Extend the prototype (or a new one) to a list-heavy package (`Wel`,
   `Chd`) to measure the `MutableMapping`/Item-list surface this one
   skipped.
2. Prototype the codegen-side change: emit `Field(json_schema_extra=...)`
   from `flopy4/mf6/utils/codegen/{make,filters}.py`'s templates in place
   of `attrs.field(metadata=...)` — no validator-emitting needed, per the
   corrected finding above; the existing `shape=` metadata is enough.
3. Prototype migrating one real consumer (`flopy4/mf6/netcdf.py`'s
   `_PackageSpec`, the smallest of the three) off `attrs.fields()`/
   `.metadata` to confirm the `model_fields`/`json_schema_extra` swap is as
   mechanical there as it was in this prototype, and to check the
   `Attribute.type`/`FieldInfo.annotation` question flagged above.
4. Re-decide go/no-go from (1)-(3), not from the January prototype or this
   single-package measurement alone.

## Related

- `docs/dev/prototypes/pydantic_dis_prototype.py` — the working prototype
  behind "Prototype results" above. Runnable standalone; not wired into
  flopy4's real registry/codegen/write/load path.
- `docs/dev/netcdf-spec-plan.md` — same schema-value-layering conclusion,
  applied to the NetCDF I/O object model.
- `mf6-object-model-plan.md` — the in-flight refactor this should sequence
  after.
- Issue #282.
- `origin/plan-codegen` (`a9b77e8`) — original prototype code/docs; mined
  for `pydantic_prototype.py`'s array-structuring pattern
  (`structure_array_from_value` → this prototype's `PackageBase._coerce_arrays`
  `field_validator`) when writing `pydantic_dis_prototype.py`. Its
  recommendation section is still not current; this doc supersedes it.
