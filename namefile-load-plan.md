# Plan: namefile loading via recursive structuring

## Background

This plan grew out of a review of two things:

1. PR #336 ("decouple xattree from codegen with api changes"), which rewrote
   the codegen-v2 package pipeline (`Package` subclasses: Npf, Ic, Chd, ...).
   It also added a `chunks=` parameter to `Package.load()` that wraps an
   already-eagerly-loaded numpy array in dask post hoc — this provides no
   real streaming/lazy read benefit (confirmed by the PR's own profiling
   comments) and should be removed; the eager `Package.load(path, dims)`
   path itself is worth keeping.
2. PR #284 ("input file loading", branch `load`, open, rough), which
   prototypes recursive namefile loading: `Component.load()` no longer
   manually loops over `self.children`; instead, a namefile's
   `packages`/`models`/`exchanges`/`solutiongroup` blocks are parsed as
   binding records, and a `Binding.to_component()` helper resolves each one
   by looking up its type token in an `FTYPES` registry and recursively
   calling `component_cls.load(path)`. This recursive-via-structuring
   design is good and should be adopted. However PR #284's base predates
   PR #336 by 27 commits — its `structure.py` is written against the old
   xattree-spec system (`get_xatspec`, `xattree.has`, etc.) and can't be
   merged as-is against current `develop`.

## Key correction driving Phase 0

PR #336 introduced a new, ad hoc field-metadata convention for codegen-v2
package fields (`metadata["dfn_block"]`, `metadata["schema"]`,
`metadata["oc_action"]`, detected via
`unstructure.has_dfn_metadata()`/`"dfn_block" in f.metadata`), distinct
from the metadata convention used everywhere else in the codebase
(`metadata["block"]`, set via `flopy4/mf6/spec.py`'s `field()`/`array()`/
`dim()`/`coord()` helpers, which wrap real `xattree` field descriptors from
`flopy4/spec.py`). `Model`, `Simulation`, `Gwf`, and all other hand-written
components still use the `block=` convention; only the codegen-v2-generated
leaf packages deviate.

This is confirmed to span both directions of the codec:

- Ingress: `converter/ingress/structure.py`'s `_structure_codegen_v2` reads
  `dfn_block`/`schema`/`oc_action`.
- Egress: `converter/egress/unstructure.py`'s `has_dfn_metadata()` branches
  code paths on which convention a class uses (`"Old xattree-based packages
  use 'block' as the metadata key; codegen v2 uses 'dfn_block'."`).
- `Package.__attrs_post_init__` (`package.py`) also branches on
  `"dfn_block" in field.metadata` to decide whether to run v2-specific
  post-init logic.

Having two conventions is why a generalized structuring/binding-resolution
step (needed for namefile loading) would otherwise have to understand both.
Rather than build that dual-support permanently, fix the root cause first:
realign codegen-v2 field metadata onto the established `block=`/xattree
descriptor convention. This is a **prerequisite**, not an optional cleanup
— it removes the fork before more code gets built on top of the wrong side
of it.

**Scope/risk note:** 76 generated package files currently carry
`dfn_block` metadata (all of `gwf/`, `gwt/`, `gwe/`, `prt/`, `utl/`, `exg/`
except `dis`/`disv`/`tdis`/`ncf`, which are hand-written per
`dfn2py.py`'s `_SKIP`). Fixing the generator and regenerating touches all
of them. This needs careful, incremental validation against
`test_mf6_codec.py`, `test_mf6_codegen.py`, `test_converter_structure.py`,
`test_dataframe_api.py`, and `test_row_api.py` — the test files PR #336
rewrote — since those encode the current (to-be-changed) behavior.

---

## Phase 0 — Realign codegen-v2 field metadata onto the `block=` convention

**Goal:** one field-metadata convention, used by every component, hand-written
or generated.

1. **Audit what `dfn_block`/`schema`/`oc_action` currently carry that
   `block=`/`array()`/`dim()` don't.** Specifically: block name, whether a
   field is a packagedata/period recarray (`schema` ref), oc_action
   keystring handling, griddata shape (`shape` metadata vs xattree's
   `dims=`). Produce a mapping from each ad hoc key to its equivalent (or
   needed extension) in `flopy4/mf6/spec.py`.
2. **Extend `flopy4/mf6/spec.py` / `flopy4/spec.py` if needed** — e.g. if
   packagedata/period recarray schemas or oc_action keystrings have no
   clean expression via `array()`/`field()` today, add the minimal metadata
   keys required (following the existing `block=`/`longname=`/`row_keyword=`
   /`cellid=` pattern already in `flopy4/mf6/spec.py`, rather than inventing
   a new parallel system again).
3. **Fix the generator**: `flopy4/mf6/utils/codegen/filters.py`,
   `make.py`, `templates/package.py.jinja` — emit fields via
   `flopy4.mf6.spec.field(block=...)`/`array(...)`/`dim(...)` instead of
   raw attrs `field(metadata={"dfn_block": ...})`.
4. **Restore/merge structuring logic**: fold `_structure_codegen_v2` back
   into (or replace it with) a single block-driven structuring path in
   `converter/ingress/structure.py` that reads `metadata["block"]` /
   xattree field descriptors — the same path `Model`/`Simulation`/`Gwf`
   already rely on. Keep whatever of the v2 rewrite was a genuine
   improvement (e.g. any parsing correctness fixes) by porting the fix
   into the restored path rather than discarding it wholesale.
5. **Collapse the dual-path branches**: remove `has_dfn_metadata()` from
   `converter/egress/unstructure.py` and the `"dfn_block" in
   field.metadata` branch in `Package.__attrs_post_init__`
   (`package.py`) — after step 4 there should be one path, not two.
6. **Regenerate all codegen-v2 packages**: `pixi run` the sync/codegen CLI
   (`flopy4/cli.py` → `dfn2py.make()`) across `gwf/`, `gwt/`, `gwe/`,
   `prt/`, `utl/`, `exg/`. Diff against current generated output field by
   field; expect field *declarations* to change shape (metadata keys) but
   not semantics.
7. **Re-validate**: run the full test suite, with particular attention to
   `test_mf6_codec.py` / `test_mf6_codegen.py` / `test_converter_structure.py`
   / `test_dataframe_api.py` / `test_row_api.py` / `test_chunked.py`, fixing
   or rewriting tests that encoded the now-removed `dfn_block` convention.
8. **Re-apply the `chunks=` removal** from `Package.load()` (background
   item 1 above) against the now-regenerated `package.py` — do this after
   Phase 0's regeneration, not before, to avoid rebasing it twice.

---

## Phase 1 — Generalize structuring to resolve bindings

With Phase 0 done, there is exactly one field-metadata convention, so this
phase is simpler than originally scoped — no more "check `dfn_block` OR
`block`."

Target: `component.py`, `converter/ingress/structure.py`

1. Add a component-type registry keyed by MF6 file-type token: `ftype:
   ClassVar[str | None] = None` on `Component`, populated in
   `__attrs_init_subclass__` alongside the existing `COMPONENTS` dict.
   Reuse the model-qualified-key pattern already there
   (`component.py:110-112`) to avoid collisions between e.g. `gwf.Ic` and
   `gwt.Ic`.
2. Write a `_resolve_binding` helper: given a field whose declared type is
   a `Component` subclass (or `list[...]`/`dict[str, ...]`/`Union[...]` of
   them) and a parsed row shaped `[type_token, filename, *names]`, resolve
   the target class (disambiguating `Union` members by `type_token`), then
   call `TargetClass.load(workspace / filename)` recursively.
3. Route any `block=`-tagged field whose value looks binding-shaped through
   `_resolve_binding` instead of the scalar-kwarg path in the (now single)
   structuring function.
4. Dimension propagation: check whether `flopy4/dimensions.py`'s existing
   `DimensionProvider`/`DimensionResolver`/`resolve_dims()` (already
   in-flight, uncommitted) is sufficient for "NPF picks up nlay/nrow/ncol
   from a DIS sibling loaded moments earlier during the same structuring
   pass," or needs a small load-order-aware cache. Prefer extending this
   existing mechanism over introducing a separate contextvar
   (`DimContext`) as PR #284 did.
5. Simplify `Component.load()` / `Context.load()` to drop the manual
   `for child in self.children: child.load()` loop — recursion now lives
   inside structuring (steps 2-3).

---

## Phase 2 — Wire it through Model/Simulation, prove it end-to-end

Target: `context.py`, `component.py`, one real example model

1. Decide the load entrypoint: give `Context` its own codec-based `load()`
   (parallel to `Package.load`), or — since structuring is now fully
   generic after Phase 1 — lift `Package.load()`'s body up to
   `Component.load()` as a single implementation used by everything.
2. Run `Simulation.load(path/"mfsim.nam")` against an existing example
   (`docs/examples/quickstart.py` or `twri.py`) and iterate until the full
   tree loads: Tdis, each Model with its packages, Exchanges, Solutions.
3. Confirm DIS-before-NPF/IC ordering and dims propagation (Phase 1.4)
   actually work end to end, not just in isolation.

---

## Phase 3 — Namefile grammar refinement (parallelizable, not blocking)

`basic.lark` already parses `packages`/`models`/`exchanges`/`solutiongroup`
blocks into generic `[type, fname, *names]` rows, which is sufficient input
for Phase 1-2. This phase is a validation/error-message improvement, not a
prerequisite, and can happen any time — including in parallel with Phases
1-2.

Target: `codec/reader/dfn2lark.py`, `grammar/templates/component.lark.jinja`,
`grammar/templates/macros.jinja`

1. Port PR #284's typed-record generation for `packages`/`models`/
   `exchanges`/`solutiongroup` blocks (generic `list` → typed
   `packages_record: ftype fname pname NEWLINE` etc.). This is
   generator/template-only and doesn't touch xattree or structuring, so it
   should port over close to as-is.
2. Switch the loader to `get_typed_parser()` for components with a
   validated typed grammar; keep `get_basic_parser()` as fallback.

---

## Phase 4 — Cleanup

1. Close or narrow PR #284 to the salvageable pieces (the grammar template
   diff from Phase 3, and the `FTYPES`/binding-resolution *design* — not
   its `structure.py`, which is superseded by Phase 1).
2. Port `test_mf6_load_integration.py` / `test_mf6_load_all_models.py` from
   PR #284 as acceptance tests for Phase 2, rewritten against the new
   implementation.
3. Update `docs/dev/` (several files touched by PR #284:
   `on_representations.md`, `sdd.md`, `grammar-issues.md`, etc.) to
   describe the final single-convention structuring/binding design, since
   PR #284's docs describe the old-xattree-spec version of this work.

---

## Suggested order

Phase 0 → Phase 1 → Phase 2 → (Phase 3 any time) → Phase 4.

Phase 0 is the highest-risk, highest-blast-radius step (76 generated
files, five rewritten test files) and should be done and merged on its own
before Phase 1 code gets written on top of it.
