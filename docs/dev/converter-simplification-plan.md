# Converter simplification plan (structure / unstructure)

Status: **S1, A1, A2, A3, B1 and B2 done; B3 next** (see "Phases"). Written
2026-09-22 against `fe5423c`, then revised on 2026-10-19/20 after rebasing
onto `develop` (`916c2f8b`). On 2026-10-20 the plan became two loaders
built in parallel and compared (see "Two loaders"). Done on attrs,
independent of the `pydantic-plan` migration, to see how simple the
converters can get on the current object model.

Since the first draft, `develop` has landed the Phase 0 harness and every
round-trip finding it turned up (see "History" at the end). The
simplification is now a pure refactor: no known bug depends on it, and
the round-trip suite (`test/mf6/test_mf6_io_roundtrip.py`, with an empty
`XFAIL` table) is the safety net.

## Goal

Replace the multi-pass, exception-driven ingress
(`converter/ingress/structure.py`) and the runtime-type-sniffing egress
(`converter/egress/unstructure.py`) with one schema-driven model of an MF6
block, used symmetrically in both directions. Behavior should not change
except where noted under "Representation decisions", which are separate.

## Two loaders

flopy4 has two parsers. The basic grammar (`grammar/basic.lark`) splits a
file into blocks of token rows and leaves their meaning to
`structure.py`; it's what every load uses. The typed grammars
(`grammar/generated/*.lark`, one per component, made by sync from the
DFNs) parse each field by its DFN rule. They're tested, but nothing loads
through them yet. A typed parse should give better errors for malformed
files, and it already does much of what `structure.py` does by hand:
- it sends each row to its field, telling `HEAD FILEOUT` from
  `HEAD PRINT_FORMAT` by the second token;
- it parses block headers, and words like OC's `ALL`/`FIRST`/`LAST`;
- it gives untagged rows to the block's untagged field.

Parsing alone is about as fast as basic (1.05×; parse plus transform is
1.24×; building 30 grammars takes 1.74 s once per process, see
`load-benchmarks.md`), but there's no full typed load to measure.

So this plan builds both loaders to the same standard, side by side:
- **Track A**, the basic loader with the simplified converter below,
  reading block structure from the DFN;
- **Track B**, a full typed load: the typed parse, then the post-parse
  steps (shaping, fill-forward, bindings);

and then compares the best version of each (Phase C). Whichever loses is
deleted. The two tracks share egress, the value representations, and the
name mapping (Phase S1). Neither waits on the other, so each phase below
says which track it's on.

## What's wrong today (`develop` @ `916c2f8b`)

**Ingress** (`structure_component`, `structure.py:841`) runs seven code
paths: Pass 1 keyed rows, Pass 2 block item lists, Pass 2b record-header
blocks (OBS `continuous`), Pass 3 period item lists, Pass 3b G/A period
arrays, Pass 3c repeating-block arrays (`tas`), and Pass 4 array blocks.
The DFN makes far fewer real distinctions (see "Model"), so the same work
is repeated:

- **Each pass classifies fields from their Python type annotations**
  (`item_list_type`, `repeating_array_key_type`, `block_list_type`,
  `_inner_class_type`, `is_array` + `to_field_type`) and not from the DFN
  block. The tagged/untagged split for item lists is **inferred from the
  block's size** (`structure.py:930-944`): an item list alone in its block
  takes every row, and one that shares its block is assumed to be a tagged
  list. That's the dict-block/list-block distinction again, and it's wrong
  in general. An untagged list can share its block (`solutiongroup`
  shares with `mxiter`; it gets through only because `_resolve_bindings`
  handles it separately), and a tagged list can be alone in its block.
  The DFN states taggedness directly.
- Pass 1 is a catch-all for "every raw block no other pass claims". Its
  exclusion test now has five conditions (`structure.py:1001-1007`), and
  they have to stay in sync with the other passes.
- Pass 1 matches a row's key against every field in the class
  (`structure.py:1054-1058`), not just the fields of the block the row
  is in.
- **Five different repetition paths:** Pass 2b, Pass 3, Pass 3c and
  `_resolve_bindings` (`solutiongroup`) each group a block's occurrences
  in their own way, with Pass 3 and 3c sharing `_group_repeating_rows`. A
  block with a header is a single concept in the DFN.
- **Three array-reading paths** that implement one grammar
  (`name [LAYERED]` + control record(s)): `_parse_array_block` (Pass 4),
  `_parse_readarray_period_block` (Pass 3b), and a direct
  `_read_control_record` call in Pass 3c with a hand-derived `ncpl`
  length.
- `effective_dims` is derived three times (`structure.py:1115`, `1285`,
  `1314`), but Pass 3b still gates on the raw `dims` (`structure.py:1239`),
  so G/A period arrays need dims to be threaded in from outside.
- The kwarg-name rule (`alias` vs `name`) is written out at least six
  times, and the copies disagree: Pass 2 skips `_`-prefixed aliases
  (`structure.py:1149`), the others don't.
- Load order (options/dimensions first) is implicit in the pass order. The
  context those passes build up (`kwargs` lookups for aux names and sizes,
  `_self_dims_from_kwargs`) isn't modeled.

**Egress** (`_unstructure_package`, `unstructure.py:250`) dispatches on
the runtime value type through roughly a dozen `isinstance` branches
(`unstructure.py:265-407`). It assembles period blocks on the side, and
hardcodes several cases:
- the `maxbound` property injection (`unstructure.py:414-418`, mirrored on
  ingress at `structure.py:988-989`);
- the `solutiongroup 1` hack (`unstructure.py:569-574`);
- two separate paths for packages and other components
  (`_unstructure_package` / `_unstructure_component`, with a TODO at
  `unstructure.py:506`).

**Asymmetry:** child bindings go through `_resolve_bindings` on ingress
but a separate component path on egress (`_make_binding_blocks`).

## Verified schema facts

Re-scanned on 2026-10-19 by migrating the current modflow6 DFNs
(`~/dev/modflow6` @ `524d1ac`) to `2.0.0.dev3` with devtools `9a1662ef`,
which is the version `develop` pins: 368 blocks.

- **Every block has at most one untagged field, and it's always the
  block's last field.** 244 blocks have none and 124 have exactly one.
  `sim-nam` `solutiongroup` is the only block where the untagged field
  isn't alone: tagged `mxiter`, then the untagged list.
  - The untagged fields are lists, except for `*-sto` `period.storage`
    (string) and `utl-tas` `time.tas_array` (array). Each of those is
    the only field in its block.
  - The first draft found a third non-list case in `utl-ts`
    `attributes`, caused by missing `in_record` flags. That's **fixed
    upstream** (modflow6 #3003, 2026-09-23), and flopy4 now generates
    `utl-ts` correctly. devtools' checked-in dev3 test snapshot
    (`autotest/dfns/__snapshots__/v2.0.0.dev3`) still has the old
    fields, so it needs regenerating.
- **Lists can be tagged** (devtools #368): a list is tagged when its
  item begins with a keyword. There are 54 tagged lists: `ts_filerecord`
  and `tas_filerecord` in options, OC `period.output`, and the G/A
  packages' `period.aux`. `aux`'s keys are the auxiliary names, which are
  dynamic keywords tied to the `auxiliary` option by `fk` (devtools #371).
  Repeated `TS6 FILEIN` is just a tagged list. No separate `repeats` flag
  is needed.
- **The schema enforces where untagged lists go** (devtools
  `Block._check_field_order`): at most one per block, and it must be
  last, because it consumes the rest of the block. Tagged fields,
  including tagged lists, can sit anywhere before it. Untagged non-list
  fields aren't checked yet; see "devtools follow-ups".
- **Repeating blocks (have a `header`):**

  | block | fill_forward | fields | components |
  |---|---|---|---|
  | period | yes | one untagged list | list-based stress packages |
  | period | yes | tagged list | OC (`output`) |
  | period | yes | tagged arrays + tagged `aux` list | G/A packages, `utl-spca` |
  | period | yes | one untagged string | `*-sto` |
  | time | no | one untagged array | `utl-tas` |
  | solutiongroup | no | tagged integer + untagged list | `sim-nam` |
  | continuous | no | one untagged list | `utl-obs` |

  Headers aren't always scalars. `utl-obs` `continuous` has a **Record**
  header (`FILEOUT <name> [BINARY]`), so the repetition key is parsed
  according to the header field's type, not cast as a number.
- Codegen departs from the DFN in one place. `*-sto` `period` is a
  single-untagged-string block, but codegen wraps it in an item list
  (`Sto._stress_period_data: dict[int, list[StressPeriodData]]`). MF6
  holds one value per period: `sto_rp` (`gwf-sto.f90`) reads a single
  `this%storage` string. See representation decision 1.
- **File records carry their trigger keyword** as `_keyword` metadata
  (fixed before the refactor, `fe5423c`). The row key is the record's
  keyword (`ts6`, `obs6`, `gwfhead`), not the field's py name (`ts_file`).
  That's the same name and form as a Record class's `_keyword`. Rejected
  alternatives: naming the field after the keyword (gwt-ist's
  `CIM FILEOUT` would collide with the `cim` array, and `oc.head` would
  stop saying it holds a path), and generating file records as Record
  classes (`wel.ts_file = Path(...)` is simpler to use).

## Model

### One block kind

There is no dict/list block distinction. The schema's field-order rule is
enough to parse any block:

> A block is an ordered set of fields. A body row whose first token is a
> tagged field's key belongs to that field. Every other row belongs to the
> block's untagged field, and there is at most one of those.

Every block in the corpus fits this rule without exceptions:
- options, dimensions, griddata: tagged fields only;
- list-based period blocks, `continuous`: only the untagged list;
- OC `period`, G/A `period`: tagged fields only (the arrays, the `aux`
  tagged list, OC's `output` tagged list);
- `solutiongroup`: tagged `mxiter`, then the untagged list. This is
  exactly the case the "last" rule is there to allow;
- `sto` period, `tas` time: one untagged scalar or array, as the block's
  only field.

A tagged key can come from:
- the field's name or alias;
- an inner record's `_keyword` (e.g. `Npf.Cvoptions`, `sfacrecord`);
- a path field's `_keyword` (`ts6`, `obs6`, `gwfhead`, ...);
- a tagged list's item keyword(s) (OC `output`'s `SAVE` / `PRINT`);
- a **dynamic key**: values of the field its `fk` names. The G/A `aux`
  list's keys are the parsed `auxiliary` names, which is one reason for
  the load context below.

### Repetition: within a block and of a block

These are two independent axes.

**Within a block**, a field either occurs once or repeats. In the schema,
"repeats" means "is a `List`", whether tagged or untagged:

|  | once | repeats (a `List`) |
|---|---|---|
| **tagged** | options scalars, records, griddata arrays | `ts_filerecord`, OC `output`, G/A `aux` |
| **untagged** | `sto` storage, `tas_array` | a list block's item rows |

A tagged list collects the rows its key claims, and they can be
interleaved with other fields' rows. The untagged list takes every row
that no key claims.

**Of a block**: a block with a `header` repeats.
- No header: the block value is the parsed body.
- Header: the block value is `{header_value: body_value}`, with
  `header_value` parsed according to the header field's type:
  - `iper` → 0-based kper (today's convention);
  - `time_from_model_start` → float;
  - `group_num` → int;
  - `continuous` → the header record (`list[Block]` today, see
    `block_list_type`).
- `fill_forward` is a **semantic** flag: an absent repetition means "keep
  the previous one". It affects how a field's value is assembled
  (`flopy4.mf6.period_arrays`), not how it's parsed.

This replaces Pass 2b, Pass 3, Pass 3c and the `solutiongroup` part of
`_resolve_bindings` with one grouping step.

### Value parsers, one per field type (shared by every block)

| field type | ingress (rows) | egress |
|---|---|---|
| keyword | presence → `True` | name if truthy |
| integer / double / string / file | `row[1]` (anything after it is ignored, as MF6 does) | name + value |
| record | `Record.from_tokens(row)` | `to_tokens()` |
| inline array (shape is not grid dims, e.g. `auxiliary`) | rest of row | name + values |
| grid array | control record(s) and `LAYERED`; length from the DFN `shape` resolved against dims | array writer |
| list | each claimed row → an element (an `Item` with per-row union dispatch, a `Path`, or a named array for `aux`); OPEN/CLOSE body redirect | per element |

Inline vs. grid array is already decided from shape. The three
array-reading paths merge into the grid-array parser once record length
comes from the field's DFN shape for every caller.

**Bindings** (packages, models, exchanges, solutions) are lists whose
elements are resolved into child components after parsing. That makes
them a post-parse step on the value, not a separate block kind.
`_resolve_bindings` becomes that step, and egress's
`_make_binding_blocks` is its inverse.

Unknown keys are consumed, skipped, and warned about, as today. The value
parser has to know how many rows to take (a control record spans rows),
so skipping still means parsing.

### Load context and order

`LoadContext` (workspace, dims, parent) already exists for what comes from
outside the file. What's missing is the state that builds up *within* one
load. Blocks are processed in DFN block order. Options and dimensions
always come first; this is to be asserted, not assumed. As blocks are
parsed, they accumulate:
- `naux` and auxiliary names (the `aux` dynamic keys and item column
  sizes);
- conditional-column switches (`boundnames`, ...);
- dims derived from the component's own dimensions block, for dims
  providers (`_self_dims_from_kwargs`), computed once.

This replaces the implicit dependency that pass ordering encodes today.

### Where block structure comes from (Track A)

From the DFN itself, stored with the generated classes. Sync stores the
DFNs it generated the classes from (as it did before #455, which dropped
them once the typed reader stopped needing them), and `spec.dfn(cls)`
returns a class's DFN `Component` by its `dfn_name`, cached. The class
carries only that name, so the generated code doesn't grow (flopy3 inlines
each DFN in its classes, which bloats them). The stored DFNs always match
the classes, because one sync writes both, which DFNs downloaded at
runtime wouldn't.

At runtime both directions read each block straight from the DFN
`Block`: its fields in order, `header` (field, type, `fill_forward`), and
which field is untagged. Row keys are the DFN's leading tags
(`_leading_tags`), with the second token where a first token leads two
fields (OC's `HEAD`); dynamic keys come from a field's `fk`. That's one
copy of the DFN, read in its own terms, with no flopy4-specific summary of
it. This removes all the structural sniffing: the annotation-based
classifiers on ingress, the block-size tagged-list inference, the
`isinstance` dispatch on egress, and the `fill_forward_blocks`
recomputation.

What the DFN doesn't say is which class attribute holds a DFN field
(`head_filerecord` → `head_file`, `stress_period_data` for a period
block's list). That's codegen's naming rule, and both tracks need it
(Phase S1).

The stored DFNs are a stopgap for the comparison. If Track B wins, they
go again.

## Sketch

```python
def structure_component(raw, cls, *, context=None, name=None):
    context = context or LoadContext()
    state = LoadState(context)                      # aux names, switches, self-dims
    kwargs = {}
    for block in dfn(cls).blocks.values():          # DFN order
        groups = group_rows(raw, block)             # {None: rows} | {header: rows}
        values = {h: parse_body(rows, block, state) for h, rows in groups.items()}
        kwargs |= assemble(block, values)           # unwrap / per-field dict / period_arrays
        state.update(block, kwargs)
    kwargs |= resolve_bindings(cls, kwargs, context)
    ...

def parse_body(rows, block, state):
    out = {}
    for rows_for_field, field in claim_rows(rows, block, state):  # key → field, rest → untagged
        out[field.name] = parse_value(field, rows_for_field, state)
    return out
```

Egress mirrors this. For each block spec, `serialize_value` is applied per
field, and a header block expands to `"{block} {header}"` names. The
package and component paths become one function.

## Representation decisions (separate, API-visible)

1. **STO period: DECIDED, follow the DFN; rename the field upstream to
   `stress_period_data`.** It's one value per period, so codegen stops
   wrapping it in an item list. The field becomes
   `stress_period_data: Optional[dict[int, Literal["steady-state",
   "transient"]]]` with `block="period"` and `fill_forward=True`: a block
   with one untagged field, the same shape as `tas` time. The name comes
   from the DFN; devtools' dev2 migration currently calls the merged field
   `storage` (`_collapse_sto_keywords`, `migrate_to_v2_0_0_dev2.py`). The
   user-visible change is dropping the one-row list:
   `stress_period_data={0: [("STEADY-STATE",)]}` becomes
   `stress_period_data={0: "steady-state"}`.

   Sequencing: a devtools PR renaming the field, then a dependency bump,
   then the codegen change and regenerated `*-sto` classes. **Not started**
   (devtools still says `storage`).
2. **`stress_period_data` consolidation in codegen.** Period list blocks
   already have exactly one untagged list field in the DFN, so the
   consolidation may be vestigial apart from the rename/alias. **To
   verify.**

Superseded since the first draft: "keep G/A period arrays dense". On
`develop` they're sparse per-period dicts (`{kper: array | None |
TimeArraySeriesRef}`, with `aux` as `{kper: {name: array}}`; see
`flopy4.mf6.period_arrays`). That's already the `{header: value}` shape
the model above produces, so `assemble` only applies the fill-forward and
clearing rules there.

## devtools follow-ups

None of these block Tracks A or B.

- **Extend `Block._check_field_order` to untagged fields of any type**
  (≤ 1 per block, and it must be last), and regenerate the dev3 test
  snapshot, whose `utl-ts` predates modflow6 #3003. This holds for the
  current DFNs now. The converter can then rely on the rule without a
  flopy4-side check.
- **Make `_leading_tags` / `_is_dynamic_key` public** (e.g. a
  `Field.tags` property). Track A reads row keys with them at runtime, so
  it shouldn't depend on private functions. Until then, wrap them in one
  place in flopy4.
- **For decision 1 only:** rename the merged STO field from `storage` to
  `stress_period_data` in the migration. Check the memory-source fixup in
  `migrate_to_v2_0_0_dev3.py` that refers to the dev2 rename.

## Before the phases

1. **Done. Land the in-flight converter PRs, then rebase.** #495
   (`package-naming`) is merged. #496 (`solution-models`) and #497
   (`exchange-models`) both change `binding.py`, `structure.py` and
   `spec.py`. Rebase this branch after they land. #367 (`pydantic-plan`)
   and #433 (`mypy-converters`) are deferred and will rebase onto the
   result.
2. **Done (`written-file-snapshots`). Snapshot the written files.** Load snapshots
   (`test/mf6/__snapshots__/test_mf6_load_all_models/`) pin what ingress
   produces, and the round-trip test checks that values survive
   load → write → load. Nothing pins the text egress writes, apart from
   the examples in `test/__compare__`. Phase S2 rewrites egress, so a
   formatting, row-order or block-order change would pass every test. Add
   per-model snapshots of the written files over the round-trip corpus,
   built like the load snapshots: one JSON file per model, keyed by
   written file, with large arrays collapsed to a hash so a diff shows
   which block or field changed. This lands on `develop`, separately.
3. **Benchmark baseline.** Recorded in
   [discussion #55](https://github.com/modflowpy/pyphoenix-project/discussions/55#discussioncomment-18978194),
   rerun on `develop` after #483: 13 models from 5 KB to 84 MB. Against
   flopy3, flopy4 loads 1.5–13.5× faster, writes 1.1–9.8× faster, and has
   lower peak memory on 11 of 13 models. The two exceptions are
   `test1000_751x751` (307 vs. 279 MB) and `test1005_secp` (360 vs.
   345 MB). The harness is `benchmarks/` (`test_load.py`, `test_write.py`,
   `test_memory.py`). Rerun it after A3, B3 and S2, and for Phase C. Neither phase should
   regress load or write time beyond noise, and the converter rewrite
   shouldn't widen the memory gap on those two models.

## Phases

Each phase keeps the round-trip suite, the load snapshots, the
written-file snapshots, and the touched tests green. A Track B phase keeps
them green for the typed loader too, for the components it covers.

### Shared

S1. **Loader switch and name mapping.** Done:
   - `LoadContext.loader` (`"basic"` or `"typed"`), which children's
     contexts inherit, and `load(..., loader=...)` on `Component` and
     `Package`. `read_component` (in `structure.py`) sends a file to
     `converter/ingress/typed.py` when the typed loader covers its
     component (`typed.COVERED`, empty so far), else to the basic one.
   - The tests take the loader from a `--loader` option rather than a
     parameter, so a typed run keeps the test ids, and with them the
     snapshots. The report header lists the components the typed loader
     covered. The benchmarks' `load` takes `flopy4-typed`; it joins
     `LIBRARIES` (and `report.py`'s columns) once it covers a component.
   - Codegen records the attribute it names for each DFN field
     (`make.attr_names`, `ComponentSpec.attr_names`), and the runtime asks
     it for the stored DFNs (`spec.attr_names(cls)`), so there's one rule.
     Every class attribute is some DFN field's, except a model's package
     slots, which all come from the name file's package list.

   As planned:
   - A way to choose the loader per load (e.g. `load(..., loader="basic" |
     "typed")`), with basic the default. The round-trip suite, the load
     snapshots and the benchmarks take it as a parameter, so each loader
     runs against the same tests and the same snapshots. Track B starts
     out covering a few components and falls back to basic for the rest,
     and the tests say which components each loader handled.
   - One function from a DFN field to its class attribute, which codegen
     uses to name the attribute and both tracks use to find it. Today the
     rule lives inside `make.py` (`safe_name`, record flattening, the
     period block's `stress_period_data`).

### Track A: basic loader, DFN-driven converter

A1. **Stored DFNs and a runtime accessor.** Done: `flopy4/mf6/dfns`,
   `spec.dfn(cls)`, `spec.block_keys(cls, block)` (fields by leading
   keyword, by dynamic key path, and the untagged field) and
   `spec.following_tags(f)` for keywords two fields share; the devtools
   private helpers are wrapped there. Loading the 129 stored DFNs takes
   0.16 s, once per process. The stored DFNs are the 2026-10-12 nightly's,
   which regenerate every checked-in class and grammar unchanged (the
   contract's commit `203d72f0` isn't in a local checkout);
   `test_installed_dfns_match_classes` keeps it so. The first attempt was
   dropped.

   As planned: sync stores the DFNs again
   (restoring `_store_dfns`, dropped in #455), and `spec.dfn(cls)` returns
   a class's DFN `Component`. On top of it, a cached per-class lookup of
   each block's header, untagged attribute, row keys and dynamic keys,
   read from the DFN, with tests that it agrees with the classes (every
   class attribute's block is in the DFN, every tagged field's keys
   resolve, the field-order rule holds). The tests read the stored DFNs,
   not the ones CI downloads, so DFN drift on modflow6 `develop` doesn't
   affect them. No converter changes yet.

   The first attempt had codegen emit a `BlockSpec` per block onto each
   class and rebuilt the row keys at runtime from the classes' Python
   types. That restated the DFN in a vocabulary of its own (`untagged`,
   `binding`, header type names) and needed a ranking to settle key
   clashes that the DFN either doesn't have or settles with the second
   token.
A2. **Value parsers.** Done. `_read_array` reads every grid array
   (griddata, G/A period, TAS time), its length the field's DFN shape
   resolved against the dims (`_Grid`); `_tagged_value` reads a tagged
   field's row and `parse_list` a list's rows, for every pass. Loaded
   values and written files are unchanged across the corpus (241 models).

   `FACTOR` is still applied on load and not kept, as decided in
   `write-options-plan.md` ("FACTOR isn't kept", in the archive):
   keeping it means writing `values / f`, which MF6 reads exactly but
   which isn't the user's text (`3.0000000000000004` for `3` at `FACTOR
   0.1`), and dropping it only when that's inexact makes the hint depend
   on the values. A2 kept it for a while; reverted. Periods scaling one
   file by different factors (Crinkle's recharge) hold different values,
   so are written inline, as before; with an `array_format` of
   "open/close" each is now written to a file of its own instead (see
   `write_external_arrays`).

   As planned: build one grid-array parser driven by shape,
   replacing `_parse_array_block`, `_parse_readarray_period_block` and the
   Pass 3c control-record call. Pull the keyed-row, record and list value
   parsers out of Pass 1 and Pass 2.

A3. **Ingress loop.** Done. `structure_component` reads the DFN's blocks
   in order (`_Load`), options and dimensions first (now a test,
   `test_block_order`). `_occurrences` groups a file's blocks by name and
   header in one place: a period's IPER (0-based), a TAS time, a solution
   group's number, or OBS's output record. A row goes to the field of its
   own block whose key it begins with (`block_keys`, with
   `following_tags` for OC's `HEAD`, and dynamic keys before tagged ones,
   as MF6 does). The remaining rows go to the block's untagged field, or
   for a binding block to `_resolve_bindings`, which now runs last on
   those rows. A tagged list collects its rows; a grid array is read by
   A2's reader wherever it is, a TAS reference included. One rule names
   the `__init__` argument (`_init_key`), and every array read uses the
   effective dims. Also gone: `_parse_array_block`,
   `_parse_readarray_period_block`, `_group_repeating_rows`, the
   block-size inference, and `repeating_array_key_type`.
   - Unknown words warn the same way in every block. They used to warn
     only in Pass 1's blocks, but no corpus model hits one elsewhere.
   - Several solution groups still raise, now as a general rule: a
     repeating block whose fields hold one value, not one per header.
   - Over the corpus (261 models), the load warnings and errors are
     unchanged, and the snapshots for a covering subset pass.

   As planned: replace Passes 1-4 (2b, 3b and 3c included) with the
   loop above, and `solutiongroup` grouping with the header step. Along the
   way, scope key matching to the block, unify the alias rule, and gate on
   effective dims everywhere.

### Track B: typed loader

B1. **Grammar rules named after class attributes.** Done. `make_grammars`
   names each block field's rule by its attribute from `make.attr_names`,
   as `__init__` takes it (`_stress_period_data` → `stress_period_data`),
   and an untagged list's rows by theirs too (`models`, `solutiongroup`,
   `vertices`, `continuous`), so OC parses to `{"options": {"head_file":
   ...}, "period 1": {"stress_period_data": [{"saverecord": ...}, ...]}}`.
   A union list's elements keep their arm and file order. Over the corpus
   (2582 files) every block key is an `__init__` argument except computed
   `maxbound`, ungenerated `DEV_` options, a model name file's package
   list, and TAS's time-keyed blocks. The values are still shaped as the
   DFN has them (a file record's `{"headfile": ...}`, not a path): that's
   B2.

   As planned: generate the grammars
   with the Phase S1 name mapping, so a typed parse's output is keyed by
   class attribute (`head_file`, not `head_filerecord`) and maps straight
   onto the classes. Today it's keyed by DFN name (`loads_typed` on an OC
   file gives `{"options": {"head_filerecord": {"headfile": "a.hds"}},
   "period 1": {"saverecord": [...]}}`).
B2. **Full typed load for a few components.** Done.
   `converter/ingress/typed.py` reads the typed parse into a component for
   sim-nam, gwf-nam, sim-tdis, DIS, NPF, IC, STO, CHD, RCHA, OC, OBS and TAS,
   by the class's fields alone: no DFN at runtime. A block's fields are the
   class attributes whose `block` metadata names it, read in field order
   (options and dimensions first); a period's header is 0-based, a TAS time
   a float, OBS's a record's words. What both loaders do after a block's
   values are read moved into a shared base, `ComponentLoad`: assembling a
   repeating block's values by header (block lists included), fill-forward
   clearing, the one-solution-group rule, list rows into `Item`s, row
   children, bindings, and the instance's `WriteContext`. So what's
   typed-only is the per-value step: array control records to values and
   `ArrayIO` (FACTOR, IPRN, LAYERED, OPEN/CLOSE and binary files, through
   a shared `read_array_file`), union elements into their arm's `Item` (by
   keyword), records from their parts, file records to paths or children,
   and a block's OPEN/CLOSE redirect, parsed with the component's grammar.
   Dynamic keys: the grammar's generic `aux` rule reads any `<word>
   <array>` row; its name is checked against `auxiliary` afterwards, kept
   in AUXILIARY's spelling, and warns like the basic loader if unknown.
   Unlike the basic loader, an auxiliary name that's also a field's (an aux
   named RECHARGE) parses as the field, not the aux: B3, if a file does it.
   A TAS time's array isn't recorded in `ArrayIO`, as in the basic loader
   (which reads it as the block's untagged field); both should, later.

   The transformer changed in three places: a union's value arm keeps its
   arm (`("frequency", 2)`, which a union field takes; it was `2`), a
   keyword arm its case as written (it was lower case; the basic loader
   keeps the file's), and a block's OPEN/CLOSE line reads as
   `"open/close": <path>` (it was dropped). Number terminals take a Fortran
   D exponent (`1D-5`), as MF6 does. A layered array's `netcdf` slot read
   the LAYERED tree; fixed.

   Over the corpus (261 models), 254 load with identical values, warnings
   and written files under both loaders. The other 7 are typed-grammar
   parse failures in NPF, left for B3: 4 `DEV_` options not in the DFN
   (the basic loader warns and skips them), 2 remarks containing a
   reserved word (`KNOWN_TYPED_GAPS`), and `test060_gms_ets`, which
   neither loader reads. `test_mf6_typed_loader.py` checks one file of
   each block kind and four corpus models against the basic loader.

   As planned: From the typed parse to
   component kwargs, for a set covering each block kind in "Repetition":
   DIS, NPF, IC, CHD (list period), RCHA (G/A period, with `aux`), OC
   (tagged-list period), OBS (record header), TAS (double header), STO,
   and the simulation and model name files (bindings, `solutiongroup`).
   What's left after the parse:
   - shaping values: grid arrays to the grid's dims, `LAYERED` and
     OPEN/CLOSE into `ArrayIO`, `FACTOR` applied, item rows into `Item`s;
   - fill-forward and clearing, through `flopy4.mf6.period_arrays`;
   - bindings, resolved into child components (the same post-parse step as
     Track A's);
   - dynamic keys: a G/A `aux` row is keyed by an `auxiliary` name, which
     a grammar made before the file was read can't know. Check how the
     typed grammar parses those rows today, and settle it here (a generic
     rule whose key is checked against `auxiliary` afterwards, say).
   Shaping and fill-forward read the class's own fields, so there's no
   DFN at runtime.
B3. **All components.** Extend B2 to every generated component, until the
   typed loader passes the whole round-trip suite and the load snapshots
   with no fallback to basic.
B4. **Grammar build cost.** Building the grammars is the typed loader's
   cold-start cost (1.74 s for 30 components). Cache the built parsers
   (lark's `cache` option, or parsers serialized at sync time), and build
   each only when a file of its component is first read.

### Shared: egress

S2. **Egress mirror.** Unify the package and component paths. Remove the
   `maxbound` injection (move it to codegen or keep it as a field), the
   `solutiongroup 1` hack, and the `isinstance` dispatch. Egress doesn't
   depend on the loader, so this can go ahead on either track's schedule,
   reading block structure through A1's accessor (or, if Track B wins, the
   classes' fields and the Phase S1 name mapping).

### C: compare

C. **Pick a loader.** Once A3 and B3 are done, and each has had its own
   tuning, compare them over the same corpus:
   - correctness: both pass the round-trip suite and produce identical
     load snapshots;
   - load time and peak memory, with the `benchmarks/` harness on the
     standard tier, against the baseline in "Before the phases";
   - cold start, including Track A's DFN loading and Track B's grammar
     builds;
   - errors: a small set of malformed files (a missing `END`, a misspelled
     keyword, a value of the wrong type, a short list row, a bad
     OPEN/CLOSE path), comparing what each loader reports and where;
   - size: the code each loader needs from parse to kwargs.

   Write the results up next to `load-benchmarks.md`, decide, and delete
   the losing loader. If Track B wins, the stored DFNs and A1's accessor
   go too, and egress reads the classes' fields.

### Later

- **STO period representation** (decision 1) once devtools has the
   rename, and, if it checks out, the `stress_period_data` consolidation
   (decision 2), each as its own change. Both loaders produce the new
   shape if both still exist.

## Related, outside the converter

- **Developer-mode fields need a release/develop switch on sync.** The
  corpus uses `DEV_*` options (NPF `DEV_OMEGA`, IMS `DEV_PTC_*`, LAK
  `DEV_*`, MAW `DEV_PEACEMAN_EFFECTIVE_RADIUS`). Classes are generated
  without them, so ingress warns "no field takes ..." and drops them.
  Codegen already has a `developmode` flag (`make_modules`,
  `dfn2py.py --developmode`, default off), but `flopy4 sync`
  (`_sync.py`) never passes it, so it can't be turned on through the
  supported path. Expose it on `sync`, like flopy3's codegen option, and
  decide which mode the checked-in classes use. With dev fields
  generated, the converter handles them like any other field; nothing in
  this plan changes.

## Out of scope

- The index-domain / time-dimension sentinel discussion (deliberately
  dropped).

## History

The first draft's Phase 0 survey (load → write → reload over 239 corpus
models) found ten pre-existing issues (write-ups dropped once resolved; see this
file's git history). All are fixed on `develop`:
- #1 ISO datetimes, #2 float precision, #3 model subdirectories, #4
  trailing tokens, #5 single-name `AUXILIARY`: fixed directly;
- #6 aux-named G/A period arrays (`fk`-keyed `aux`, devtools #371), #7
  repeated `TS6` (tagged lists, devtools #368), #8 TAS-sourced period
  arrays (`TimeArraySeriesRef`, #413): each has a targeted test in
  `test_mf6_io_roundtrip.py`;
- #9 ungenerated packages: SFR, UZF, MAW, etc. are now generated;
- #10 quoted strings (#462).

The Phase 0 harness itself is `test/mf6/test_mf6_io_roundtrip.py`.
