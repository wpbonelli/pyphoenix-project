# Converter simplification plan (structure / unstructure)

Status: **prerequisites in progress** (see "Before Phase 1"). Written
2026-09-22 against `fe5423c`, then revised on 2026-10-19/20 after rebasing
onto `develop` (`916c2f8b`). Done
on attrs, independent of the `pydantic-plan` migration, to see how simple
the converters can get on the current object model.

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

### Where block structure comes from

Codegen already has the DFN `Block` and reads `tagged`, `header` and
`fill_forward` from it (`utils/codegen/make.py`, `filters.py`). It should
emit a per-class block spec alongside the fields, for example by extending
`spec.blocks_dict` or adding a class-level `__blocks__`. Each entry
records:
- block name;
- header field name, type and `fill_forward`;
- the tagged fields and their keys (static, or an `fk` for dynamic ones);
- the untagged field, if any.

At runtime both directions read that spec. This removes all the structural
sniffing: the annotation-based classifiers on ingress, the block-size
tagged-list inference, the `isinstance` dispatch on egress, and the
`fill_forward_blocks` recomputation.

## Sketch

```python
def structure_component(raw, cls, *, context=None, name=None):
    context = context or LoadContext()
    state = LoadState(context)                      # aux names, switches, self-dims
    kwargs = {}
    for block in block_specs(cls):                  # DFN order
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

None of these block Phases 1-4.

- **Extend `Block._check_field_order` to untagged fields of any type**
  (≤ 1 per block, and it must be last), and regenerate the dev3 test
  snapshot, whose `utl-ts` predates modflow6 #3003. This holds for the
  current DFNs now. The converter can then rely on the rule without a
  flopy4-side check.
- **Optional:** make `_leading_tags` / `_is_dynamic_key` public (e.g. a
  `Field.tags` property), so codegen takes each field's row keys from the
  spec instead of re-deriving them for the block spec.
- **For decision 1 only:** rename the merged STO field from `storage` to
  `stress_period_data` in the migration. Check the memory-source fixup in
  `migrate_to_v2_0_0_dev3.py` that refers to the dev2 rename.

## Before Phase 1

1. **Land the in-flight converter PRs, then rebase.** #495
   (`package-naming`) is merged. #496 (`solution-models`) and #497
   (`exchange-models`) both change `binding.py`, `structure.py` and
   `spec.py`. Rebase this branch after they land. #367 (`pydantic-plan`)
   and #433 (`mypy-converters`) are deferred and will rebase onto the
   result.
2. **Snapshot the written files.** Load snapshots
   (`test/mf6/__snapshots__/test_mf6_load_all_models/`) pin what ingress
   produces, and the round-trip test checks that values survive
   load → write → load. Nothing pins the text egress writes, apart from
   the examples in `test/__compare__`. Phase 4 rewrites egress, so a
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
   `test_memory.py`). Rerun it after Phases 3 and 4. Neither phase should
   regress load or write time beyond noise, and the converter rewrite
   shouldn't widen the memory gap on those two models.

## Phases

Each phase keeps the round-trip suite, the load snapshots, the
written-file snapshots, and the touched tests green.

1. **Block spec from codegen**, with a runtime accessor and tests that it
   matches the DFN (including the field-order rule). No converter changes
   yet.
2. **Value parsers.** Build one grid-array parser driven by shape,
   replacing `_parse_array_block`, `_parse_readarray_period_block` and the
   Pass 3c control-record call. Pull the keyed-row, record and list value
   parsers out of Pass 1 and Pass 2.

   Along the way, keep an external array's `FACTOR` in its `ArrayIO`.
   Today the loader multiplies the factor into the values, so periods that
   read one file with different factors (`test017_Crinkle`'s
   `Array.MF-RechDIST.txt`, ten periods) load as ten different arrays,
   and the writer falls back to writing them inline. The values are right,
   but the shared file is lost. With the factor recorded, egress can write
   `OPEN/CLOSE <file> FACTOR <f>` back per period.
3. **Ingress loop.** Replace Passes 1-4 (2b, 3b and 3c included) with the
   loop above, and `solutiongroup` grouping with the header step. Along the
   way, scope key matching to the block, unify the alias rule, and gate on
   effective dims everywhere.
4. **Egress mirror.** Unify the package and component paths. Remove the
   `maxbound` injection (move it to codegen or keep it as a field), the
   `solutiongroup 1` hack, and the `isinstance` dispatch.
5. **STO period representation** (decision 1) once devtools has the
   rename, and, if it checks out, the `stress_period_data` consolidation
   (decision 2), each as its own change.

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

- Switching ingress from the basic token-row parser to the typed DFN
  grammar (`codec/reader`, `loads_typed`). The typed grammar would
  eventually take over the control-record, OPEN/CLOSE and `LAYERED`
  handling now in `structure.py`. The per-field value parsers above are
  the seam where that change would plug in, so this refactor should make
  it smaller, but it's not a prerequisite.
- The index-domain / time-dimension sentinel discussion (deliberately
  dropped).

## History

The first draft's Phase 0 survey (load → write → reload over 239 corpus
models) found ten pre-existing issues, recorded in `ROUNDTRIP-FINDINGS.md`
and the `finding-*.md` files. All are fixed on `develop`:
- #1 ISO datetimes, #2 float precision, #3 model subdirectories, #4
  trailing tokens, #5 single-name `AUXILIARY`: fixed directly;
- #6 aux-named G/A period arrays (`fk`-keyed `aux`, devtools #371), #7
  repeated `TS6` (tagged lists, devtools #368), #8 TAS-sourced period
  arrays (`TimeArraySeriesRef`, #413): each has a targeted test in
  `test_mf6_io_roundtrip.py`;
- #9 ungenerated packages: SFR, UZF, MAW, etc. are now generated;
- #10 quoted strings (#462).

The Phase 0 harness itself is `test/mf6/test_mf6_io_roundtrip.py`.
