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

`docs/dev/prototypes/pydantic_dis_prototype.py` ports `Dis` (via
`DisBase`/`Package`/`Component`/`DimensionResolverMixin`,
`flopy4/mf6/gwf/{dis,disbase}.py`, `flopy4/mf6/{package,component}.py`,
`flopy4/dimensions.py`) to pydantic in its current, post-`Row` shape, and
runs (`pixi run -e dev python docs/dev/prototypes/pydantic_dis_prototype.py`)
against real assertions: derived dims (`nodes`/`ncpl`/`nvert`) compute
correctly, griddata scalar defaults broadcast to full arrays, a child
component (`ncf`, stubbed) gets parent-wired, `validate_assignment=True`
catches a bad post-construction assignment, and (v3, below) an explicit
`nodes=` kwarg is correctly rejected. It is a scoped-down measurement, not
a drop-in replacement — see "Explicitly out of scope" below.

v3 of the prototype is built on `pydantic.dataclasses.dataclass`, not
`pydantic.BaseModel` — see "BaseModel vs. pydantic dataclasses" below for
why that switch happened and what it fixed.

**What ported cleanly, lower cost than expected:**

- Parent/child wiring is *simpler* in pydantic than attrs, not just
  equivalent: attrs needs a private-attribute naming convention (`_parent`
  field, `parent=` constructor kwarg, via leading-underscore mangling) to
  get a public-looking accessor; pydantic just names the field `parent`
  directly. No trick needed.
- `attrs.fields(cls)` → a pydantic dataclass's `__pydantic_fields__`
  (or `cls.model_fields` if targeting `BaseModel`), `.metadata` dict →
  `Field(json_schema_extra={...})`: a direct, mechanical swap, field by
  field. Every place `spec.py`'s `field()` helper writes to `metadata[...]`
  has an equally-simple pydantic equivalent.
- The single post-construction hook (`__post_init__` on a pydantic
  dataclass) not auto-chaining across the MRO (each override must call
  `super().__post_init__()` itself) turned out to be a wash, not a new
  cost — attrs' `__attrs_post_init__` already required the same explicit
  `super()` chaining discipline, and it's the same *single*-hook shape
  attrs has (unlike BaseModel's two-hook `model_validator(mode="after")` +
  `model_post_init` split — one more reason v3 prefers dataclasses).
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
  `ncpl`/`nvert`/`nodes` — computed, never user-supplied) has **no working
  `BaseModel` equivalent** — this was v2 of the prototype's biggest
  unresolved gap, and it's resolved in v3 by targeting
  `pydantic.dataclasses.dataclass` instead. See "BaseModel vs. pydantic
  dataclasses" below.
- `attrs.Factory(lambda self: ..., takes_self=True)` (`Component.name`'s
  default: the lowercased *runtime* class name) has no direct
  `default_factory=` equivalent (those callables take no arguments) in
  either BaseModel or a pydantic dataclass — filled in inside the single
  post-construction hook instead (`__post_init__`, on the dataclass; a
  `model_validator(mode="after")` on the now-abandoned BaseModel version).
  One extra method either way, where attrs needed a one-line `Factory` —
  the only place this measurement found pydantic costing a genuinely
  unavoidable few extra lines versus attrs.

**Explicitly out of scope for this measurement (deferred, not glossed
over)** — each of these is real remaining migration surface, not yet
priced:

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

## Prototype results: list-heavy package (2026-09-16)

`docs/dev/prototypes/pydantic_chd_prototype.py` prices out the two things
the `Dis` prototype explicitly deferred: `Component`'s full `MutableMapping`
interface for a *list*-kind child field (several packages in one slot, not
just `Dis.ncf`'s single-child case), and `Package`'s Item-list period-data
coercion, modeled on the real `Chd`/`Chd.StressPeriodData`
(`flopy4/mf6/gwf/chd.py`). Run via
`pixi run -e dev python docs/dev/prototypes/pydantic_chd_prototype.py`.

**The MutableMapping half ports cleanly**, once one attrs convention is
matched exactly: `Component._is_default_child_name()`'s check — is this
child's `.name` still at its class-name default, not just `is None` — has
to be replicated verbatim. Pydantic's dataclass `__post_init__` already
defaults every child's `.name` before the parent ever sees it (same as
`ComponentBase.__post_init__` in the `Dis` prototype), so by the time a
list-kind parent's `_set_child_parents()` runs, `child.name` is never
actually `None` — a naive `is None` check silently fails to disambiguate
same-class siblings (confirmed by running this prototype with that bug in
place: two fresh `ChdProto()` children both landed on `"chd1"` for their
would-be `"chd0"`/`"chd1"` names, since only the second matched `used`).
Fixed by porting the real `_is_default_child_name` equality check instead.
Once that's right, `__getitem__`/`__setitem__`/`__delitem__`/`__iter__`/
`__len__`, auto-naming (`f"{field}{i}"`), and parent-stamping on
`__setitem__` all behave identically to `Component`'s real semantics
(demo asserts construction-time naming, explicit-key replacement, and
deletion all work).

**The Item-list half surfaces one real, new problem pydantic-specific to
this field shape, not the array-field one already solved:** attrs applies
zero validation to a field like `Chd._stress_period_data` (no
validator/converter declared) — raw tuples/dicts pass through attrs'
`__init__` untouched, and `Package.__attrs_post_init__` coerces them
afterward. A plain pydantic-typed equivalent
(`Optional[dict[int, list[Row]]]`) does NOT behave this way: it's eagerly,
strictly validated at construction, so the exact raw-tuple/raw-dict input
`Chd(stress_period_data=...)` accepts today raises
`ValidationError: Input should be an instance of Row` before any
post-init coercion hook runs — confirmed directly, including a control
case proving the identical field without the fix does reject the identical
input the fixed version accepts. `pydantic.SkipValidation[...]` fixes it
(confirmed: same raw input accepted, coercion still runs in
`__post_init__` exactly like the attrs version), at two small, genuinely
new costs:

- `flopy4/mf6/item.py`'s `item_list_type()` needs one extra unwrap step
  (`Annotated[X, SkipValidation()]` → `X`) before its existing
  `get_origin`/`get_args` walk reaches `dict[int, list[Row]]` — confirmed
  the real function's current logic doesn't do this and would silently
  return `None` (no item type found) without it. Small, mechanical,
  one-time addition to one function.
- `SkipValidation` also opts the field out of `validate_assignment`
  re-validation, confirmed directly (`pkg.stress_period_data = "junk"` is
  silently accepted). Not a regression versus attrs (no validator is
  declared on this field today either), but it is a per-field, explicit
  opt-out rather than something that falls out of the shared config the
  way array-field coercion does.

**Corollary, worth stating plainly: `flopy4/mf6/item.py`/`record.py` (the
`Item`/`Record` row-type subsystem — token round-tripping,
`construct_item`/`construct_union_item`, cellid/aux/boundname handling) do
not need to migrate to pydantic at all.** With `SkipValidation`, pydantic
never inspects what's inside the list — `ChdRowProto` in this prototype is
a genuine, unmodified `attrs.define` class, exactly like the real
`Chd.StressPeriodData`. A real migration can leave `item.py`/`record.py`
attrs-based indefinitely and only port `Component`/`Package` (and
generated leaf classes) to pydantic — a materially smaller migration
surface than porting the whole object model in one pass would suggest.

**Still out of scope after this measurement:** the keystring-union-arm
case (`construct_union_item` — LAK/SFR/MAW/UZF period settings, several
`Item` subclasses sharing one field via a `Union`) — this prototype only
covers the plain (non-union) coercion path `Chd`/`Wel`/`Drn`-style packages
use. `Component`'s "dict"-kind child collection (as opposed to "list") is
also still unexercised, though nothing found here suggests it would behave
differently from the "list" case's `_children`/naming logic.

## Item/Record: does it need attrs? (2026-09-16)

The previous section's corollary said `item.py`/`record.py` don't *need*
to migrate — true, `SkipValidation` means a `Package` that's moved to
pydantic can leave them alone indefinitely. Direct question asked
separately: if they *did* move, would they need to stay on attrs, could
they target plain stdlib `dataclasses.dataclass`, or does pydantic work
here too? `docs/dev/prototypes/pydantic_record_prototype.py` ports
`Record`'s core mechanics (`to_tokens`/`from_tokens`, the metadata-driven
field walk `record_fields()` does) to a pydantic dataclass and answers
this directly — run via
`pixi run -e dev python docs/dev/prototypes/pydantic_record_prototype.py`.

**Nothing here requires attrs specifically.** Grepped the real codebase
first: no Record/Item field anywhere declares `validator=`/`converter=`
(those only appear on `Component`/`Package`-level fields, e.g. `Gwf.dis`'s
`convert_grid`) — `_coerce()` does its own manual, explicit coercion,
called directly from `from_tokens()`, never wired through attrs machinery.

**One real attrs-specific behavior IS load-bearing, and it's not the one
the array-field/Item-list prototypes hit:** `_nested_class()` exists
because a composed record field (e.g. `Oc.Headprint.fmt: "Oc.Format"`,
generated by `package.py.jinja` lines 38/40 as a literal, fully-qualified
string) names a **sibling class inside the same enclosing class** —
unresolvable via any module-global lookup at class-body-execution time,
since Python class bodies can't see sibling names in an enclosing class's
scope. attrs' default behavior of leaving `f.type` as the literal,
unevaluated string is exactly what makes `_nested_class()`'s lazy,
custom qualname-walking resolution possible.

- **Confirmed this is NOT attrs-specific**: plain stdlib
  `dataclasses.dataclass` does the identical thing — `dataclasses.fields
  (cls)[i].type` is *also* just the raw, unevaluated string, since it's a
  property of how Python stores a string-literal annotation, not of
  attrs. A straight port to stdlib dataclasses needs zero changes to
  `_nested_class()`.
- **Pydantic dataclasses behave differently, but not how a first guess
  ("eager resolution breaks forward refs") would suggest.** Confirmed by
  testing the *exact* problem shape — `Format` referencing `Headprint`
  declared in the *harder* order (referencing class first, referenced
  class second, source-order matching what real codegen's
  `spec.inner_classes` loop isn't guaranteed to avoid): pydantic defers
  schema-building for an unresolvable annotation
  (`cls.__pydantic_complete__` is `False` right after decoration) and
  resolves it **lazily** — constructing an instance with **no explicit
  fixup call at all** just works, self-healing on first use (the same
  effective mechanism `typing.get_type_hints()` uses: `eval()` against the
  defining module's globals plus qualified attribute access, succeeding
  once `Oc.Format` exists as a real attribute of `Oc`, regardless of
  which class was defined first in source). The one real gap: something
  that inspects `__pydantic_fields__` **before any instance is ever
  constructed** — exactly what `from_tokens()` does (calls
  `record_fields(cls)` before building the instance it returns) — sees
  the annotation still as an unresolved `ForwardRef`. Fixed with one
  guarded `pydantic.dataclasses.rebuild_dataclass(cls)` call inside
  `record_fields()` itself — small, centralized, confirmed working even
  with zero prior instances of the target class.
- **Genuine win for pydantic over stdlib dataclasses here, not just
  parity:** once resolved, a pydantic dataclass's `FieldInfo.annotation`
  **is the real class object**, not a string — confirmed
  `fields["fmt"].annotation` is identical (`is`) to `Optional[Oc.Format]`
  built directly. That means `_nested_class()`'s entire ~15-line custom
  qualname-walking resolver (`sys.modules` lookup, `__qualname__`
  splitting, `getattr` walk) becomes **unnecessary code**, replaced by
  `isinstance(annotation, type) and issubclass(annotation, RecordBase)`
  (after unwrapping `Optional`) — confirmed working in the prototype's
  `_nested_class()`. A stdlib-dataclass port would have to *keep*
  `_nested_class()` unchanged, same as attrs today.

**Everything else is the same mechanical swap already established
elsewhere in this doc, confirmed again here:**

- `attrs.NOTHING` (the `required_tagged` sentinel in `from_tokens()`) →
  `FieldInfo.is_required()`. Direct swap.
- `attrs.asdict(row)` (`Package.to_dataframe()`) → `dataclasses.asdict
  (row)` works **unchanged** on a pydantic dataclass instance, confirmed
  — pydantic dataclasses are real stdlib dataclasses underneath.
- Positional construction (`construct_item`'s `item_cls(*values)`,
  `cls(*before, tuple_vals)`) needs `kw_only` left at its default
  (`False`), unlike `Component`/`Package`'s `kw_only=True` — confirmed
  working, matching attrs' current non-`kw_only` `Item`/`Record` classes.
- `.metadata` → `Field(json_schema_extra={...})`, the same convention
  already chosen for `Component`/`Package` (not a stdlib-style
  `Field(metadata={...})` kwarg — confirmed that's deprecated/unsupported
  on pydantic's `Field()`). One metadata idiom across the whole object
  model, not two.

**Consequence:** if/when `item.py`/`record.py` ever do migrate, target
`pydantic.dataclasses.dataclass`, not plain stdlib `dataclasses.dataclass`
— it's not just equally viable, it deletes real code
(`_nested_class()`'s custom resolver). But per the corollary in the
previous section, migrating them is still not *required* by a
`Component`/`Package` migration — `SkipValidation` decouples the two, so
this can be sequenced independently, or skipped entirely, without
blocking anything else in this plan.

## BaseModel vs. pydantic dataclasses

Every pydantic-based sketch this codebase has produced so far — the
January prototype, `flopy4/mf6/netcdf.py`, `modflow_devtools.dfns` — is
built on `pydantic.BaseModel`. v2 of this prototype followed that default
without examining it. It shouldn't have: `pydantic.dataclasses.dataclass`
is the closer match to what the object model actually needs, confirmed
directly (not assumed) by testing both:

- **`Field(init=False)`.** On `BaseModel`, it's accepted by the field
  constructor but has **no runtime effect at all** — confirmed:
  `M(nodes=999)` on a `BaseModel` with an `init=False` field silently
  succeeds and sets `nodes=999`, even under `extra="forbid"`. It's
  type-checker-only metadata there (part of `@dataclass_transform`
  support), not an enforced constraint. On a pydantic dataclass, the
  *identical* `Field(init=False)`, combined with `extra="forbid"` in
  config, works exactly like attrs: `DisProto(nodes=999)` raises
  `ValidationError: Unexpected keyword argument` — confirmed in the demo.
  This was v2's single biggest unresolved gap; v3 closes it for free, no
  extra code beyond the `Field(init=False)` call attrs' equivalent already
  needed.
- **Everything else composes cleanly, confirmed with standalone tests
  before committing to the rewrite:** a pydantic dataclass subclassing
  `ABC` and mixing in `collections.abc.MutableMapping` works
  (`isinstance(d, MutableMapping)` is `True`); `kw_only=True` is a direct
  decorator argument, matching `@attrs.define(kw_only=True)` exactly;
  `field_validator`/`validate_assignment=True` work identically to the
  `BaseModel` case; direct `self.__dict__[...]` writes (the
  `_dimension_cache` lazy-init pattern `flopy4/dimensions.py` uses today)
  and `object.__setattr__` bypass-writes (used throughout
  `Package`/`DisBase` to update a field without re-triggering validation)
  both still work on a dataclass instance; a nested pydantic-dataclass-typed
  child field (`ncf: Optional[NcfProto]`) constructs and wires up the same
  as under `BaseModel`.
- **What a dataclass gives up:** `BaseModel`'s self-methods
  (`.model_dump()`, `.model_validate()`, `.model_json_schema()`) aren't
  available directly on an instance — the equivalent is an external
  `pydantic.TypeAdapter(cls)` call. In practice this costs nothing here:
  flopy4 doesn't lean on those methods today either. `Component.to_dict()`
  already wraps `attrs.asdict(self, recurse=True, filter=...)` — an
  external function, not a self-method — and would wrap
  `TypeAdapter(type(self)).dump_python(self, ...)` the same way. JSON
  Schema (already concluded, in the Background section above, to belong
  at the devtools/DFN layer rather than here) would still be reachable via
  `TypeAdapter(cls).json_schema()` if ever wanted.

**Consequence:** any future prototyping or real migration should target
`pydantic.dataclasses.dataclass`, not `BaseModel`. It's a closer structural
match to attrs (single post-construction hook, real `init=False`,
`kw_only` as a decorator arg) and gives up nothing flopy4's object model
actually uses from `BaseModel`.

## Supporting-code complexity vs. the current implementation

The previous section (and the ~50-call-site count above) covers *how many*
places need to change. This is about the code *those places rely on* —
`spec.py`'s `field()`/`fields_dict()`/`to_field_type()`/`get_field_type()`
and `attrs_xarray.py`'s `child_field_candidates()` — and whether its
replacement is more, less, or equally complex.

- **The bulk of it is a wash.** `to_field_type()`/`get_field_type()`
  (~100 lines) and `child_field_candidates()` (~40 lines) are `match`
  statements over `get_origin()`/`get_args()` of a raw type annotation,
  bridging Python's type system to MF6's own DFN type vocabulary
  (`keyword`/`integer`/`double`/`record`/`list`/...). That complexity comes
  from interpreting `typing` module generics, not from attrs vs. pydantic —
  confirmed directly: a side-by-side test showed `attrs.Attribute.type` and
  pydantic's `FieldInfo.annotation` expose `Optional[int]`-style
  annotations identically (`typing.Optional[int]`,
  `typing._UnionGenericAlias`, both cases). Neither library's native
  validation/schema machinery reduces this bridge layer — MF6's type
  vocabulary doesn't map onto either library's own type system, so a
  hand-written translation is required either way. `spec.py`'s `field()`
  metadata wrapper is the same story: `Field(json_schema_extra={...})` in
  place of `attrs.field(metadata={...})`, same kwargs, same size.
- **One place pydantic's introspection is more robust, not just
  equivalent** — found by testing, not assumed: `attrs.fields(cls).type`
  only resolves to a real type object when attrs can eagerly evaluate the
  annotation. A string/forward-ref annotation (e.g. under `from __future__
  import annotations`, which the codebase doesn't use today but easily
  could add) silently degrades `attrs.Attribute.type` to an unresolved
  `str` unless `attrs.resolve_types()` is called explicitly — and there
  are zero such calls anywhere in flopy4 today, so `to_field_type()`/
  `child_field_candidates()` are quietly relying on a convention (no
  future-annotations import) rather than a guarantee. Confirmed directly:
  `b: "int | None"` under attrs stayed a bare `str`; the identical
  annotation under pydantic resolved to a real `types.UnionType`
  automatically, no extra call needed.
- **One place pydantic dataclasses need genuinely new support code:** the
  `init=False` replacement (see "BaseModel vs. pydantic dataclasses" above)
  is resolved for the object model itself, but confirms this is a
  systemic pattern, not a `Dis`-only quirk — `init=False` appears at 13
  real sites across 7 files, including `flopy4/mf6/utils/codegen/
  filters.py` (codegen emits it, not just hand-written `DisBase`). A real
  migration's codegen templates need `extra="forbid"` in the shared
  dataclass config (one line, project-wide) for this to keep working —
  cheap, but worth naming as a required config decision, not an implicit
  default.

## Re-assessed recommendation

The measurement doesn't change the "wait for a trigger" recommendation
above. It does relocate where the real cost lives: not in per-field
boilerplate (the array-coercion validator collapses to one reusable
definition, not one per field or per package), not in translating type
annotations to MF6's DFN vocabulary (a wash — see "Supporting-code
complexity" above), and not in `Component`/`Package`'s own object-model
mechanics (`MutableMapping`, Item-list coercion, parent/child wiring — all
now measured and ported cleanly, at the cost of one `SkipValidation`
opt-out per Item-list field and one small `item_list_type()` fix), but in
(a) the ~50-call-site consumer surface outside the object model itself
(`netcdf.py`, `converter/*`, `codec/*`) and (b) the still-unmeasured
keystring-union-arm coercion path (LAK/SFR/MAW/UZF-style period settings).
Both are one-time, codebase-wide costs rather than a cost that scales with
how many packages get migrated. Target `pydantic.dataclasses.dataclass`,
not `BaseModel`, for both — and leave `flopy4/mf6/item.py`/`record.py`
attrs-based; they don't need to migrate (see the Item-list corollary
above).

## Next steps (when picked up for a real migration decision)

1. Prototype the codegen-side change: emit `Field(json_schema_extra=...)`
   from `flopy4/mf6/utils/codegen/{make,filters}.py`'s templates in place
   of `attrs.field(metadata=...)` — no validator-emitting needed, per the
   corrected finding above; the existing `shape=` metadata is enough. Make
   sure the emitted `@dataclass(...)` config carries `extra="forbid"` (see
   "Supporting-code complexity" above — required for `init=False` to work)
   and that Item-list fields get `SkipValidation[...]` wrapped in.
2. Prototype migrating one real consumer (`flopy4/mf6/netcdf.py`'s
   `_PackageSpec`, the smallest of the three) off `attrs.fields()`/
   `.metadata` to confirm the `__pydantic_fields__`/`json_schema_extra`
   swap is as mechanical there as it was in this prototype.
3. Measure the keystring-union-arm coercion path (`construct_union_item`)
   against a real package that uses it (LAK, SFR, MAW, or UZF).
4. Re-decide go/no-go from (1)-(3), not from the January prototype or these
   two single-package measurements alone.

## Related

- `docs/dev/prototypes/pydantic_dis_prototype.py` — the working prototype
  behind "Prototype results" above, built on `pydantic.dataclasses.dataclass`
  (v3 — see "BaseModel vs. pydantic dataclasses"). Runnable standalone; not
  wired into flopy4's real registry/codegen/write/load path.
- `docs/dev/prototypes/pydantic_chd_prototype.py` — the list-heavy-package
  prototype behind "Prototype results: list-heavy package" above (imports
  `ComponentBase`/`PackageBase` from `pydantic_dis_prototype.py`). Runnable
  standalone.
- `docs/dev/prototypes/pydantic_record_prototype.py` — the `Record`/`Item`
  prototype behind "Item/Record: does it need attrs?" above. Self-contained
  (doesn't import from the other two prototypes). Runnable standalone.
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
