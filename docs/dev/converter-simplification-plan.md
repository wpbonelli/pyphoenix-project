# Converter simplification plan (structure / unstructure)

Status: **in progress, Phase 0** (written 2026-09-22 against `fe5423c`;
line refs updated 2026-09-23). Done on attrs, independent of the
`pydantic-plan` migration, to see how simple the converters can get on the
current object model.

## Goal

Replace the multi-pass, exception-driven ingress (`converter/ingress/structure.py`)
and the runtime-type-sniffing egress (`converter/egress/unstructure.py`) with
one schema-driven model of an MF6 block, used symmetrically in both
directions. Behavior should not change except where noted under
"Representation decisions", which are separate and opt-in.

## What's wrong today

**Ingress** runs six code paths: Pass 1 keyed rows, Pass 2 item lists,
Pass 3 period item lists, Pass 3b G/A period arrays, Pass 3c repeating-block
arrays (tas), Pass 4 griddata. The DFN has far fewer real distinctions
(see below), so the same work is done repeatedly:

- Pass 1 is a catch-all "every raw block no other pass claims". It uses a
  four-condition exclusion test (`structure.py:696-701`) that has to stay in
  sync with the other passes.
- `_parse_griddata_block` and `_parse_readarray_period_block` are
  near-duplicates of one grammar: `name [LAYERED]` + control record(s). They
  differ in record length (field shape vs. hardcoded `ncpl`), in layer
  assembly (flat concat vs. `(nlay, ncpl)` stack), and in the TAS /
  unknown-name skips.
- Repeating-block row grouping is done twice (Pass 3, Pass 3c). Effective
  dims / `ncpl` are derived four times.
- The kwarg-name rule (`alias` vs `name`) appears five times, and the copies
  disagree: Pass 2 skips `_`-prefixed aliases, the others don't.
- Pass 1 matches a row's keyword against every field in the class, not just
  the fields of the block it's in.
- Pass 3b gates on the raw `dims` argument, not `effective_dims`, so G/A
  period arrays are silently dropped if dims weren't threaded in.
- Ordering (options/dimensions before everything else) is implicit in pass
  order, not stated as an invariant.

**Egress** dispatches on runtime value type (`ndarray` / `dict` /
`list[Item]`), assembles period blocks on the side, and hardcodes several
cases: `f.name == "aux"`, `f.name == "auxiliary"`, the `maxbound`
property injection, and the `solutiongroup 1` hack. Packages and other
components go through two separate functions (`_unstructure_package` and
`_unstructure_component`; there's a TODO to unify them).

**Asymmetries:**
- Egress writes G/A per-aux-name period arrays, but ingress parses and then
  discards them, so a load/write round trip loses them.
- Child bindings are `_resolve_bindings` on ingress but a separate component
  path on egress.

## Verified schema facts (DFN dev3 corpus, 2026-09-22)

I scanned all 368 blocks via `LocalDfnRegistry(...).spec(schema_version="2.0.0.dev3")`:

- **242 blocks have no list field, 125 have exactly one list field and
  nothing else, and 1 has a list plus another field:** `sim-nam`
  `solutiongroup`, which holds `mxiter` (integer, tagged) and
  `solutiongroup` (list). No block has more than one list field.
- **Every block has at most one untagged field.** 237 blocks have none and
  131 have exactly one. List fields are always untagged. The non-list
  untagged fields are:
  - `gwf/chf/olf-sto` `period.storage` (string, only field in its block)
  - `utl-tas` `time.tas_array` (array, only field in its block)
  - `utl-ts` `attributes.interpolation_method_single`, in an 8-field block.
    **Confirmed as a DFN bug, not a real exception.** In modflow6's
    `utl-ts.dfn`, `method`, `interpolation_method_single` and `sfac` are
    missing `in_record true`, although they're members of
    `interpolation_methodrecord_single` (`METHOD <x>`) and
    `sfacrecord_single` (`SFAC <x>`). The dev3 conversion therefore leaves
    them as top-level fields: `interpolation_methodrecord_single` ends up
    with no fields and `sfacrecord_single` is missing `sfac`. With the flag
    fixed, `attributes` has no untagged top-level field. flopy4 doesn't
    generate a `utl-ts` class yet, so nothing is affected today. The fix
    belongs upstream in the modflow6 DFN (not filed).
- **Types of non-list fields:** keyword 469, record 250, array 207,
  integer 128, string 115, double 102, file 3.
- **Repeating blocks (have a `header`):**

  | block | fill_forward | fields | components |
  |---|---|---|---|
  | period | yes | one list | 48 |
  | period | yes | arrays | 8 (the G/A packages + `utl-spca`) |
  | period | yes | one untagged string | 3 (`*-sto`) |
  | time | no | one untagged array | `utl-tas` |
  | solutiongroup | no | integer + list | `sim-nam` |
  | continuous | no | one list | `utl-obs` |

  Headers aren't always scalars. `utl-obs` `continuous` has a **Record**
  header (`FILEOUT <name> [BINARY]`), so the repetition key has to be parsed
  by the header field's type, not cast as a number.
- Codegen already departs from the DFN in one spot. `*-sto` `period` is a
  single-untagged-string block in the DFN, but codegen synthesizes a
  `stress_period_data: dict[int, list[StressPeriodData]]` item list for it
  (`make.py` `period_schema` branch). MF6 holds exactly one value per
  period: `sto_rp` (`gwf-sto.f90`) reads a single `this%storage` string and
  sets `iss` from `STEADY-STATE` / `TRANSIENT`. The v1 DFN has two separate
  keywords; dev3 merges them into one `storage` string with `valid`
  values. A list is therefore the wrong shape.
- **Tagged dict entries can repeat.** A dict block is normally
  one-row-per-key, but MF6 accepts some keys several times and accumulates
  them. `TS6 FILEIN <f>` is the known case: IDM's `load_io_tag`
  (`LoadMf6File.f90:737-749`) appends each `FILEIN` path to a growing
  array, and the list/keystring loaders register every file
  (`Mf6FileList.f90:85-91`). TDIS explicitly limits `ATS6` to 0 or 1
  (`tdis.f90:423`), which shows the general mechanism allows more. The DFN
  doesn't say which keys repeat: `ts_filerecord` is a plain record. The
  corpus has 2 such files: `test051_uzfp2TS/uzfp2.uzf` (2 × `TS6`) and
  `test106_tsnodata/alt_model/model.wel` (5 × `TS6`).
- **Bug found while checking this, now FIXED (ahead of the refactor):**
  ingress dropped *every* block-level file record, not just the repeats.
  The row key is the record's trigger keyword (`ts6`, `head`, ...), but
  codegen names the field `ts_file` / `head_file`, so Pass 1 never
  matched. Egress guessed the keyword from the py name, which was wrong
  for 138 of the 223 file records in the DFN corpus (`TS FILEIN` instead
  of `TS6 FILEIN`, and likewise `OBS6`, `GRB6`, ...).

  The fix: path fields now carry the trigger keyword as `_keyword`
  metadata, lowercase. That's the same name and form as a Record class's
  own `_keyword` ClassVar. It replaces the separate `prefix=(...)` tuple
  that LAK/SSM row-level path columns used, so there's one spelling
  everywhere. Codegen sets it from the record's single Keyword child, or
  for a tagged bare File (prt-fmi `GWFHEAD FILEIN <f>`) from the field's
  own name. It raises if a record has anything other than exactly one
  keyword. Both converters read it, and hand-written path fields
  (model-level `netcdf_*`, dis/disv `ncf6`) set it explicitly.

  Alternatives considered and rejected (2026-09-22):
  - **Naming the path field after the keyword** (`ts6`, `head`), so the
    name is the row key like any other tagged field. Rejected for two
    reasons. First, gwt-ist would collide: the `CIM FILEOUT` record and the
    `cim` griddata array would share one name. Second, many keywords are
    also quantity names (`oc.head`, `oc.budget`, `sfr.stage`), so the
    attribute would no longer say it holds a path.
  - **Not flattening file records**, i.e. generating them as Record classes
    with their own `_keyword`. Rejected for API ergonomics:
    `wel.ts_file = Path(...)` is simpler to use than a record object.

  The metadata is the flattened record's structure (`_keyword` +
  `direction`) carried on the field.

## Model

### One block kind, with at most one untagged field

The review started from four block kinds: keyed rows, item list, tagged
arrays, bare array. Those collapse to two:

- **Dict block**: entries keyed by field name. Each entry's value is parsed
  according to its field's type, so griddata arrays are just dict entries
  whose values span several rows (control records, optionally `LAYERED`).
- **List block**: a single list field; the body is rows of items.
- A dict block with only one field can leave it untagged (`sto` storage,
  `tas_array`), in which case the whole body is the value.

The facts above allow a further step that also covers `solutiongroup`
without a special case:

> A block is a set of fields, **at most one of which is untagged**. A body
> row whose first token names a tagged field (or its alias, or a record's
> keyword) belongs to that field. All other rows form the untagged field's
> body.

Under this rule:
- options, dimensions and griddata have tagged fields only;
- a list block is the untagged-only case, with the body parsed as item rows;
- `sto` period and `tas` time have one untagged scalar or array, with the
  body parsed as that value;
- `solutiongroup` is tagged `mxiter` plus an untagged list, and needs no
  exception.

These rules describe the same thing; they differ only in whether
`solutiongroup` needs its own exception. **DECIDED (2026-09-23): adopt the
single rule.**

A tagged key can come from:
- the field name or alias;
- an inner record's `_keyword` (e.g. `Npf.Cvoptions`, `sfacrecord`);
- a path field's `_keyword` (`ts6`, `obs6`, `gwfhead`, ...), the same
  concept as a Record class's `_keyword` (see the bug fixed above);
- **auxiliary names**: in G/A period blocks, `<auxname> [LAYERED]` rows are
  entries of the `aux` array field. The key set comes from the parsed
  `auxiliary` option, which is one reason the load context below exists.

**Repetition is a field-level property too, independent of taggedness.** A
repeating block repeats as a whole, with a header. A repeating *field* can
occur on several rows of one block occurrence:

|  | once | repeats |
|---|---|---|
| **tagged** | options scalars, records, griddata arrays | `TS6 FILEIN` |
| **untagged** | `sto` storage, `tas_array` | a list field's item rows |

A list field is therefore just an untagged, repeating record-shaped field.
It doesn't need its own block kind.

A repeating field does **not** have to be alone in its block. `TS6` sits in
`options` with a dozen other fields, and that's fine because each of its
rows names itself. The constraint that matters is on *untagged* fields,
repeating or not: an untagged row can't say which field it belongs to, so
there can be at most one untagged field per block, and it takes every row no
tagged key claims. `solutiongroup` (tagged `mxiter` plus an untagged list)
shows the untagged field doesn't have to be alone either. **Validation rule
for codegen:** ≤ 1 untagged field per block. It holds across the corpus
once the `utl-ts` DFN bug is fixed.

A tagged field that repeats collects its rows into a list. That needs a
per-field `repeats` flag, which the DFN doesn't carry yet. It's being added
to devtools at the field level (not the block level); flopy4 picks it up
with a devtools bump (see open questions).

Unknown keys are consumed and skipped as today. The value parser has to
know how many rows to take (a control record spans rows), so a skip still
has to parse.

### Value parsers, one per field type (shared by every block)

| field type | ingress (rows) | egress |
|---|---|---|
| keyword | presence → `True` | name if truthy |
| integer / double / string / file | `row[1]` | name + value |
| record | `Record.from_tokens(row)` | `to_tokens()` |
| inline array (shape is not grid dims, e.g. `auxiliary`) | rest of row | name + values |
| grid array | control record(s) and `LAYERED`; length from DFN `shape` resolved against dims | array writer |
| list | rows → `Item`s (union dispatch per row); OPEN/CLOSE body redirect | `to_tokens()` per item |

Inline vs. grid array is already decided from shape (`35a8209`). The
griddata and G/A period array parsers merge into the grid-array value
parser once record length comes from the field's DFN shape. G/A period
fields have that shape since step 1 of the netcdf work.

**Bindings** (packages, models, exchanges, solutions) are list blocks whose
items are resolved into child components after parsing. That makes them a
post-parse step on the value, not a separate block kind. `_resolve_bindings`
becomes that step, and egress's `_make_binding_blocks` is its inverse.

### Repetition: an independent axis

- No header: the block value is the parsed body.
- Header: the block value is `dict[header_value, body_value]`, with
  `header_value` parsed by the header field's type:
  - `iper` → 0-based kper (today's convention);
  - `time_from_model_start` → float;
  - `group_num` → int;
  - `continuous` → the header record's value.
- `fill_forward` is a **semantic** flag: an absent repetition means "keep
  the previous one". It affects only how a field's value is assembled
  (densifying G/A arrays today, see below), not parsing.

### Load context and order

Blocks are processed in DFN block order. Options and dimensions always come
before data blocks; this is to be asserted, not assumed. A small context
accumulates as blocks are parsed:
- `naux` and auxiliary names;
- `boundnames`;
- dims: threaded from a sibling, or derived from the component's own
  dimensions block (the `_self_dims_from_kwargs` case for dims providers);
- `workspace`.

This replaces the implicit dependency that the pass ordering encodes today.

### Where block structure comes from

Codegen already has the DFN `Block`. It should emit a per-class block spec
alongside the fields, for example by extending `spec.blocks_dict` or adding a
class-level `__blocks__`. Each entry records:
- block name;
- header field name, type and `fill_forward`;
- the tagged field names and keys (including aliases and record keywords);
- the untagged field, if any.

At runtime both directions read that spec. This deletes all the structural
sniffing:
- `item_list_type` / `repeating_array_key_type` / `_inner_class_type`
  classification on ingress;
- `isinstance` dispatch on egress;
- the `fill_forward_blocks` recomputation in `structure.py`.

## Sketch

```python
def structure_component(raw, cls, *, dims=None, workspace=None, name=None):
    ctx = LoadContext(dims=dims, workspace=workspace)
    kwargs = {}
    for block in block_specs(cls):                  # DFN order
        groups = group_rows(raw, block)             # {None: rows} | {header: rows}
        values = {h: parse_body(rows, block, ctx) for h, rows in groups.items()}
        kwargs |= assemble(block, values)           # unwrap / per-field dict / densify
        ctx.update(block, kwargs)                   # naux, aux names, boundnames, self-dims
    kwargs |= resolve_bindings(cls, kwargs, ctx)
    ...
```

Egress mirrors this. For each block spec, `serialize_body` is applied per
field, and a header block expands to `"{block} {header}"` names. The
package and component paths become one function.

## Representation decisions (separate, API-visible)

The following aren't needed for the refactor, but the refactor makes them
cheap and exposes them:

1. **Dense G/A period arrays: DECIDED, keep dense.** Every other repeating
   field is `dict[header, value]`, but G/A period arrays stay dense
   `(nper, ...)` arrays padded with `FILL_DNODATA`, with fill-forward
   encoded as "all-sentinel period ⇒ omit the block". `assemble`
   densifies them on ingress, and egress splits them back into per-period
   blocks. This is the only field whose runtime shape differs from its
   parsed shape, and it's confined to the assemble/split step. netcdf
   export keeps working unchanged.
2. **STO period: DECIDED, follow the DFN, and rename the field upstream to
   `stress_period_data`.** It's one value per period (see verified facts),
   so codegen stops synthesizing an item list around it. The field becomes
   `stress_period_data: Optional[dict[int, Literal["steady-state",
   "transient"]]]` with `block="period"` and `fill_forward=True`. It's a
   dict block with one untagged field, the same shape as `tas` time.

   Naming: MF6's STO period block names no field. It has two optional
   keywords, stored by IDM as the separate flags `steady_state` /
   `transient` (`gwf-stoidm.f90:311-339`). The name `storage` came from
   devtools' dev2 migration (`_collapse_sto_keywords` in
   `migrate_to_v2_0_0_dev2.py`), which merged the two keywords into one
   string field. Today's `Sto.stress_period_data` comes from flopy4's
   codegen item-list synthesis. Decision: **rename the merged field to
   `stress_period_data` in the devtools migration**. flopy4 codegen keeps
   taking names from the DFN, with no STO special case, and the user-facing
   name stays the same as today and matches every list-based period
   package. The only user-visible change is dropping the one-row list
   around each value: `stress_period_data={0: [("STEADY-STATE",)]}`
   becomes `stress_period_data={0: "steady-state"}`.

   Sequencing: first a devtools PR renaming the field (check
   `migrate_to_v2_0_0_dev3.py:1428`'s memory-source fixup, which mentions
   the dev2 rename), then a dependency bump, then the codegen change and
   regenerated `*-sto` classes. Examples and tests that build STO period
   data need the small value-shape update.
3. **`stress_period_data` consolidation in codegen.** Period list blocks
   already have exactly one list field in the DFN, so the consolidation may
   be vestigial apart from the rename/alias. **To verify.**

## Phases

Each phase keeps the full suite green (`pixi run -e dev pytest -n auto test`).

**Sequencing (proposed 2026-09-23).** Phase 0 and some of the fixes it
exposes land on `develop` first, each on its own branch from a worktree
under `~/dev/`, before the simplification starts on this branch. Finding
numbers refer to `ROUNDTRIP-FINDINGS.md`.

- **On develop, first:**
  1. Phase 0 harness: a full-corpus round trip with strict xfails grouped
     by cause, plus targeted source-vs-loaded tests for #6, #7 and #8.
  2. #1 tokenizer ISO datetimes. It hides 21 models, including the
     aux-array cases, from the round trip.
  3. #3 writer model subdirectories.
  4. #2 writer float precision: make the default lossless (DECIDED).
  5. #4 trailing tokens and #5 single-name `AUXILIARY` (DECIDED: fix on
     develop). They're small Pass 1 patches for silent data loss, and the
     logic carries over into the Phase 2 value parsers.
- **Left to the simplification:** #6 aux-named period arrays (Phase 3),
  #7 repeated `TS6` (Phase 3, after the devtools `repeats` bump), and #8
  TAS-sourced period arrays (after its representation decision).
- **Separate:** #9 skipped ungenerated packages (codegen coverage).

Once the develop work lands, rebase this branch onto it. Phase 0 below is
then done, and Phases 1-5 proceed as written.

0. **Characterization tests.** Add load → write → load round trips over a
   corpus subset covering every row of the repeating-blocks table, plus
   griddata, `LAYERED`, OPEN/CLOSE, the aux-named G/A arrays, and the two
   repeated-`TS6` files. Mark as known xfails:
   - the aux-named G/A period arrays, which ingress skips as unknown names
     (`structure.py:347`), so they're lost on round trip;
   - repeated tagged keys: each `TS6 FILEIN` row overwrites the last
     (`structure.py:714`), so only the last file survives.

   Single file records (`TS6`, `OBS6`, ...) are no longer dropped; that was
   fixed in `fe5423c`, so they're ordinary passing cases.
1. **Block spec from codegen**, with a runtime accessor and tests that it
   matches the DFN. No converter changes yet.
2. **Value parsers.** Build one grid-array parser driven by shape, replacing
   `_parse_griddata_block` and `_parse_readarray_period_block`. Pull out the
   keyed-row, record and list value parsers from Pass 1 and Pass 2.
3. **Ingress loop.** Replace Passes 1–4 with the loop above. Along the way,
   fix block-scoped key matching, the alias inconsistency, the `dims` gate,
   aux-named arrays, and file-record keys and repeats. That flips the
   Phase 0 xfails.
4. **Egress mirror.** Unify the package and component paths. Remove the
   `aux` / `auxiliary` name checks, the `maxbound` injection (move it to
   codegen or keep it as a field) and the `solutiongroup 1` hack.
5. **STO period representation** (decision 2) and, if it checks out, the
   `stress_period_data` consolidation (item 3), each as its own change.

## Phase 0 survey (2026-09-23)

Load → write → reload over the 239 non-`large` `KNOWN_PASSING` corpus
models, comparing every block field of every component (loaded vs.
reloaded): **183 identical, 31 differ, 25 fail to write.** Every cause is
pre-existing. Details, affected models and fix directions are in
`ROUNDTRIP-FINDINGS.md` and the `finding-*.md` files at the repo root. That
includes one finding not listed here: packages without a generated class
(SFR, UZF, MAW, ...) are silently skipped on load, so the survey can't see
them.

In refactor scope, fixed by the value parsers (Phase 2) or ingress loop
(Phase 3):
- **Scalar/keyword rows with trailing tokens** (~20 models). Inline
  comments (`PRINT_INPUT (echo input to listing file)`) and extra values
  (IMS `under_relaxation none dbd`, `outer_maximum 100 500`) become lists,
  because Pass 1 keeps `row[1:]` when `len(row) > 2`. Egress then drops
  them, or fails to write them (3 IMS files). A keyword should be
  presence → `True` and a scalar should be `row[1]`, as in the
  value-parser table.
- **Single-name `AUXILIARY`** (7 models). `AUXILIARY CONCENTRATION` loads
  as a string, not a list, so egress's `auxiliary` list branch skips it
  and it's lost. This is the inline-array value parser.
- **Aux-named G/A period arrays** (`structure.py:347`) and **repeated
  `TS6`** (`structure.py:714`), as already listed.
- **TAS-sourced G/A period arrays** (`RECHARGE TIMEARRAYSERIES <name>`,
  test027). Ingress consumes and discards the reference
  (`structure.py:343`), so the period reads as all-`FILL_DNODATA` and
  egress omits it. Not listed before. It needs a **representation
  decision**: the dense `(nper, ...)` array has no way to say "period k
  comes from TAS `<name>`".

Out of converter scope, but they hide converter coverage:
- **Tokenizer splits ISO datetimes** (21 models fail to write TDIS).
  `START_DATE_TIME 1997-07-16T19:20:30.45+01:00` tokenizes as
  `[1997, '-07-16T…']`. This blocks round-trip checking of the whole
  model, including `test001h_rch_array1` (the aux-array case).
- **Writer float precision.** Arrays are written to ~8 significant
  digits (`11.09305553` → `11.0930555`), so values change on round trip
  (`delr`, `delc`, `strt`; 3+ models).
- **Writer doesn't create model subdirectories** (`test031_many_gwf`).

Not a bug: a constant array loaded 0-d (`sto.sy = 0.15`) reloads
broadcast to full shape. The comparison should treat these as equal.

Loaded-vs-reloaded comparison can't see an ingress drop that loses the
value on both sides (aux arrays, TAS refs, `TS6` repeats). Those need
targeted source-vs-loaded assertions.

## Open questions

- Which tagged keys can repeat? `TS6 FILEIN` is confirmed. Other `FILEIN`
  records (e.g. `OBS6`) go through the same IDM `load_io_tag` path, so they
  probably accumulate too, but the package code may use only the first
  one. The DFN has no flag for this. Options:
  - ask devtools/mf6 for one (e.g. a record-level `repeats` or `shape`);
  - treat every `FILEIN` record as repeatable in flopy4, a narrower rule
    grounded in `load_io_tag`.

  Either way the field type becomes `list[Path]` for repeatable ones, which
  is a user API change.

  **In progress (2026-09-23):** a field-level `repeats` attribute is being
  added upstream in devtools. Which fields get it is decided there.
- Codegen should enforce ≤ 1 untagged field per block, as it already
  enforces ≤ 1 fill-forward block. That's the plan; the only question is
  timing. The `utl-ts` DFN bug has to be fixed upstream first, or `utl-ts`
  exempted until then.
- `codec/writer/filters.py` still reads a `prefix` attr off xarray
  DataArrays (lines ~284, ~334), from a legacy Dataset row path. Nothing
  sets it anymore, so it's probably dead. Remove it during Phase 4.

## Out of scope

- Switching ingress from the basic token-row parser to the typed DFN
  grammar (`codec/reader`, `loads_typed`). The typed grammar would
  eventually take over the control-record, OPEN/CLOSE and `LAYERED`
  handling now in `structure.py`. The per-field value parsers above are
  the seam where that change would plug in, so this refactor should make
  it smaller, but it's not a prerequisite.
- The index-domain / time-dimension sentinel discussion (deliberately
  dropped).
