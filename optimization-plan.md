# Plan: input-load optimizations, remaining work

Rewritten 2026-10-26. The original plan (2026-09-29; in history at the
`load-baseline` branch, `249df5b9`) is mostly done. Steps 1-5 are done or
dropped; steps 6-11 (added 2026-10-26, from profiling) are next. Index of
related work: `loader-roadmap.md`.

## Done (for reference)

| original step | landed in | notes |
|---|---|---|
| 0. snapshot check | #481 | numpy snapshots in the load tests (`test/mf6/__snapshots__/`) |
| 1. lazy imports | #483 | `flopy` and `xugrid` no longer imported on the load path. `import flopy4.mf6.simulation` is ~1.3 s, ~0.9 s of it xarray (+ pandas, numpy) |
| 3. bulk numeric runs | #474, #479, #481, #484 | arrays lexed as one token in both grammars, including string arrays; possessive terminal; column-wise list tables; ragged rows grouped |
| 5a. inline transformer | #483 | basic parser transforms as it parses |
| benchmark infra | #482 | `benchmarks/` (tiers, memray, `bench-report`, `bench-profile`); `docs/profile/` removed |

## Ground rules

- One worktree per step under `~/dev/`, off `develop`.
- `pixi run -e dev ...`; verify with `pixi run -e dev smoke`. Ask before
  full-suite or benchmark runs.
- Sign commits with the session's trailers. No pushes, PRs or GitHub
  actions unless asked.
- One PR per step. A PR that's about speed gives `bench --compare` numbers.

## 1. External-array reader matches MF6 (done)

`_read_open_close_values` (`flopy4/mf6/converter/ingress/structure.py`)
does `read_text().replace(",", " ").split()` and converts every token.

**What MF6 accepts.** Both the old `ArrayReaders.f90` and IDM's
`ArrayRead/*Reader.f90` read an OPEN/CLOSE text array with Fortran
list-directed input, `read(unit, *) (arr(j), j=1, n)`. Checked with gfortran:

| input | MF6 (real) | MF6 (int) | flopy4 today |
|---|---|---|---|
| whitespace, tabs, blank lines, commas (`1, 2`) | ok | ok | ok |
| `D`/`d` exponents (`1d0`) | ok | error | error |
| exponent without letter (`1.0+1` = 10) | ok | error | error |
| repeat counts (`3*7`) | ok | ok | error |
| `/` ends the read | ok, rest unset | ok, rest unset | error |
| values after the first N (incl. text) | ignored | ignored | error if non-numeric |
| fewer than N values | error (EOF) | error | silently short |
| null value (`1,,3`) | entry unset | entry unset | values shift |
| `#` / `!` comments, `;`, quoted numbers | error | error | error |
| `1.0` in an integer array | — | error | error |

So the original plan's "tolerate comments" idea is wrong: MF6 rejects
comments in external arrays. The gaps are the other way round.

**Change.** A reusable helper, text in, flat ndarray out, with the expected
count:
- Fast path: split on whitespace and commas, take the first N tokens,
  convert with numpy. Used when the text has no `*` or `/` and no
  null values (cheap C-level checks).
- Fallback: `D` exponents, letter-less exponents, repeat counts, `/`.
- Errors: fewer than N values ("expected N values for <field>, got M"),
  null values and `r*` nulls (flopy4 has no previous value to keep), and
  a bad token, named.
- Extra trailing values are ignored, as in MF6.

**Tests:** unit tests for each row of the table; smoke.

**Inline arrays too.** MF6 reads INTERNAL arrays with the same
list-directed `read`, so the reader is shared: `array_values` in
`codec/reader/transformer/rows.py`, used by `_read_control_record` for
both, and by the typed transformer. NUMBERS now lexes repeat counts.
Inline arrays now error on too few values and on non-integers in integer
arrays (they were silently short or truncated). No corpus snapshot changed.

Status: done on branch `external-array-reader`
(`~/dev/pyphoenix-external-arrays`), PR #513.

Later on the same branch:
- One number parser: `parse_number` reads reals via `fortran_float`.
- A repeat count in a list row errors, saying so.
- OPEN/CLOSE files are read in `flopy4/mf6/external.py` (`read_array_file`,
  `read_list_file`, `read_binary_list_file`), beside writing them.
  `structure.py` keeps thin wrappers. Next: `external-ref-plan.md`.

**Letter-less exponents everywhere.** Standard Fortran (`F` editing) reads
`1.0+1` as 10.0, and MF6 reads every real that way. `flopy4.utils.fortran_float`
does too, used for arrays (`_numeric_prefix`, `array_values`), time-series
list columns (`to_ts_value`: `1.0+1` was a series name) and other doubles
(new `to_double` converter: a scalar like `OUTER_DVCLOSE 1.0-6` stayed a
string). Not in the basic transformer's per-token test, which doesn't know
the field's type: `1-2` must stay a word for a string field (a boundname).
The typed grammar's `double` takes D and letter-less exponents
(`FORTRAN_REAL`); `NUMBER`, in untyped list tokens, doesn't.

**Performance** (1M values vs. `develop`, min of 3): lexing NUMBERS +0-7%;
inline floats even, inline ints -15% (no float intermediate); external
whitespace-separated even; comma-separated +19% (null-value search). Loads
of henrytidal, Keating and biscqtg_disv within noise.

## 2. Lark flags (done, on the same branch)

- `debug=True` dropped: no measurable change in build or parse time (it
  keeps lark's slower `ParseTable`, but bulk tokens leave the parser few
  steps).
- Cache per grammar in `grammar/__lark_cache__/` (not lark's default, the
  shared temp dir, which would load another user's pickle). Basic parser
  build ~16 -> ~1.2 ms; 26 typed grammars ~1.1 s -> ~140 ms. Parsing
  unchanged.

## 3. Lists with words: measured, dropped

Corpus load (258 models, branch `external-array-reader`, exclusive times):

| stage | time | share | per row |
|---|---|---|---|
| parse | 7.40 s | 23.5% | |
| list blocks of numbers (by column) | 6.34 s | 20.1% | 0.7 us (9.46M rows) |
| list blocks with words (row by row) | 0.57 s | 1.8% | 5.9 us (96K rows) |
| everything else | 17.21 s | 54.6% | |
| total | 31.52 s | | |

Parsing rows with words: 3.3 us/row against 0.3 for numbers only
(100K CHD rows, with and without boundnames). So words cost ~9 us/row in
all, ~0.9 s of the corpus (~3%). Not worth a reader of its own. Per row,
the slow ones are GNC (45 us), OBS (29), list unions (27) and LAK tables
(509, nested file loads included), all small. The bigger target is the
"everything else" bucket, which is outside this plan.

## 4. Results in `load-benchmarks.md` (skipped for now)

Its Results section is still the `fe5423c` baseline (corpus 14.44 s, cold
start 2.41 s). Re-run `bench` (and cold start) on current `develop` and add
measured numbers per regime: inline arrays, external arrays, simple lists,
complex lists, cold start.

## 5. Weekly benchmark CI job (done, on the same branch)

- `.github/workflows/benchmark.yml`: Mondays and `workflow_dispatch`
  (`ref`, `tiers`, `record`); `standard` and `large` tiers; models and
  DFNs cached; CPU and `bench-report` in the job summary; run JSON
  uploaded for 90 days; `benchmarks/history.py` -> `github-action-benchmark`
  history on `bench-data` (flopy4 times, flopy4 / flopy3 ratio, cold start;
  130% alerts that don't fail). Only scheduled runs, or manual runs on
  `develop` with `record`, add to the history.
- Before the first recording run, create the `bench-data` branch on
  `upstream` (the command is in `docs/dev/load-benchmarks.md`, "In CI").
- `ci.yml` `bench-smoke`: the smoke tier, timed (~15 s). Not
  `--benchmark-disable`, which skips every benchmark (`conftest.py`).
- Found while checking it: the parse benchmarks were broken on
  `develop`. `BASIC_PARSER` takes bytes since #483, so every file was
  dropped and the corpus came out empty. Fixed (`3aad5a05`).
- `bench-smoke` passes on PR #513 (1m12s). `benchmark.yml` hasn't run
  yet (it can't record until `bench-data` exists).

## Next steps (6-11): profiled 2026-10-26

Profiled on `external-array-reader` (`c69fa707`), not a `bench` run:
cProfile of `Simulation.load`, warm (each model loaded once first)
unless noted. Models: the smoke tier plus Keating and wtdecay ("small"),
and `test1001_Peterson` + `test1002_biscqtg_disv_dev` ("large", 155 MB
together).

| case | time | where it goes |
|---|---|---|
| Keating, fresh interpreter: import | 0.57 s | xarray ~0.41 s, `modflow_devtools.dfns` ~0.105 s |
| Keating, first load | 0.41 s | **0.33 s `_import_components()`** |
| Keating, second load | 0.037 s | the actual work |
| 6 small models, warm | 0.22 s | Lark ~0.08 s; the rest structuring and introspection |
| 2 large models, warm | 3.90 s | regex 1.14 s, item rows ~0.6 s, numpy parse ~0.7 s |

So for a user loading one model in a script, ~94% of the time is fixed
cost; for large models, it's lexing and per-row Python objects. The
"everything else" bucket in step 3 is mostly 6, 7 and 9 below.

Suggested order: 6 (trivial), 7, 8, 9, 10. 11 is ideas, not yet steps.

### 6. Cache `fields_dict` in `Item.__attrs_post_init__`

`Item.__attrs_post_init__` (`flopy4/mf6/item.py`, ~line 942) calls
`attrs.fields_dict(type(self))` once per row whenever the class has
counted fields: 108K calls, 0.16 s exclusive on the large models (cell2d
rows, mostly). It depends only on the class.

**Change.** Have `_counted_fields` (already `lru_cache`d) return what the
loop needs, i.e. only the `(count_name, array_field)` pairs whose
`count_name` is a column, so the per-row work is the loop alone.

**Tests:** smoke. **Bench:** biscqtg_disv load.

### 7. Cold start: import only the components a model uses

`get_ftypes()` (`flopy4/mf6/component.py`, ~line 49) calls
`_import_components()` (`flopy4/mf6/__init__.py`), which imports every
generated module: 347 attrs classes, ~0.65 ms each, 0.08 s of it
`compile()` of attrs' generated methods. `exg/__init__` alone is 0.21 s
(`gwfgwf` 0.10 s, `gwtgwt` 0.06 s), for models with no exchanges too.
`get_fnames()` does the same.

**Change.**
- `flopy4 mf6 sync` (codegen) also writes a static index, e.g.
  `flopy4/mf6/_index.py`: ftype token and DFN name -> `(module, class)`,
  with the same disambiguation `get_ftypes` does today (`_qualify` /
  `_prefix` for tokens shared between model types). Generated, so it
  can't drift from the classes; a test checks it against a full import.
- `get_ftype` / `get_ftypes` / `get_fnames` resolve through the index and
  import one module per lookup. `get_ftypes()` returning the full map
  stays available (imports everything) for callers that need it; check
  which do, and move the load path off it.
- The model packages' `__init__`s (`gwf/`, `gwt/`, `gwe/`, `prt/`,
  `chf/`, `olf/`, `exg/`, `utl/`) must become lazy too, with the same
  module `__getattr__` as `mf6/__init__`. Otherwise importing
  `flopy4.mf6.gwf.dis` still runs `gwf/__init__`, which imports every gwf
  package. Their `__init__`s are generated, so it's a template change.
- Anything that walks `FNAMES` at import or relies on registration side
  effects (subclass hooks filling `FNAMES`) needs auditing first; that's
  the main risk.

**Smaller import cuts, same PR or next:**
- `flopy4/mf6/package.py` imports `dim_input`, `dim_value` and
  `split_bound` from `modflow_devtools.dfns` at module level. That pulls
  `dfns.migrate` (~53 ms) and `dfns.registry` (~47 ms), and prints the
  experimental-API `FutureWarning`. Import inside the functions that use
  them, or import from the submodules that define them if those are light.
- xarray's own import pulls `scipy.io` (~55 ms) through `xarray.tutorial`
  -> `backends.scipy_`. Upstream; check whether a newer xarray defers it.
  Making xarray itself lazy on the load path is a much bigger change
  (`accessor.py`, `attrs_xarray.py`, `package.py` all import it at the top)
  and isn't proposed here.

**Expected:** first load ~0.41 -> ~0.1 s for Keating; cold
single-model load (import + load) ~1.0 -> ~0.5 s.

**Tests:** smoke; a test that the index matches a full import; a
subprocess test that loading a GWF-only model doesn't import
`flopy4.mf6.exg.gwfgwf` (check `sys.modules`). **Bench:** `test_cold_start`.

### 8. Fast `NUMBERS` scan, strict fallback

The regex `match` is 1.14 s of the large models' 3.9 s, nearly all the
`NUMBERS` terminal (`grammar/typed.lark`, ~line 79), whose regex checks
every number's shape. Per file (parse only):

| file | size | parse | regex |
|---|---|---|---|
| `biscayne.riv` (list rows) | 57.0 MB | 0.60 s | 0.56 s |
| `v6.evt` (arrays) | 22.9 MB | 0.16 s | 0.12 s |
| `biscayne.disv` | 9.4 MB | 0.12 s | 0.12 s |

Short rows are worst (~100 MB/s): the per-number structure dominates.
On one 570 KB period block of `biscayne.riv`:

| approach | time | throughput |
|---|---|---|
| current `NUMBERS` | 4.6 ms | 125 MB/s |
| loose character-class regex | 2.0 ms | 290 MB/s |
| line regex `(?:[ \t,]*+[-+.\d][^\n]*+\n)++` | 0.4 ms | ~1.6 GB/s |
| + `body.translate(None, b"0123456789.+-eEdD*, \t\r\n")` is empty | 0.2 ms | |

The numeric reader (`array_values`, `parse_number`) already validates
and names bad tokens, so the regex checks twice.

**Change.**
- In `_BytesLexer.match` (`codec/reader/parser.py`), before Lark's
  combined pattern: if the line starts like a number, take the
  line-regex run, then the `translate` check (letters other than `eEdD`
  -> not NUMBERS). Comment-only and blank lines inside the run need the
  same handling as today's tail (`(?:[ \t,]*+(?:[#!][^\n]*+)?\r?\n)*+`);
  a trailing comment on a data line must end the run (it lexes as a
  `line` today), so `#`/`!` mid-line fails the fast path.
- What passes the character check but isn't a number: `1-2` (a
  boundname, or a letter-less exponent), `1e`, `--`, `.`, `+`. The
  strict regex rejects these today, and the line then goes to `RECORDS`
  or `line`. Keep that: if the fast run's conversion fails, re-lex the
  run with the strict pattern. Since conversion happens in the
  transformer, not the lexer, either convert eagerly in the lexer
  (hand the transformer an array) or keep a cheap token-shape check that
  only rejects the ambiguous cases (e.g. a `[-+]` not after
  start/space/`e`/`E`/`d`/`D`, or a token with no digit). Decide by
  measuring both.
- Only the basic grammar's lexer at first; the typed grammar gets it
  when it's wired in (it imports the same terminal).

**Bolder variant, measured separately:** skip Lark for bulk bodies.
`bytes.find` the `BEGIN`/`END` lines; where the schema says a block's
body is all numeric (a list package's period block, griddata after
`INTERNAL`), hand the slice to the numeric reader. Lark sees only
headers, options and word rows. This also needs a strict-fallback path
(any word in the body -> the normal parse), and puts schema knowledge
in front of the parser, which the basic loader has avoided so far.

**Tests:** the NUMBERS/RECORDS lexing tests, plus cases for each
ambiguous token above in array and list context; smoke; corpus snapshots
unchanged. **Bench:** large tier, `test_parse`.

### 9. Per-class load plans

With imports warm, small-model loads are mostly introspection, repeated
on every load for the same classes (6 small models, 0.22 s):

| call | count |
|---|---|
| `isinstance` | 100K |
| `typing.get_args` / `get_origin` | 12K each |
| `item_list_type`, `_list_elem` | 4K each |
| `child_field_candidates` (`attrs_xarray.py`) | 2K |
| `to_field_type`, `repeating_array_key_type`, `block_list_type` | ~1.5K each |
| `structure_component` exclusive | 5 ms over 77 calls |

**Change.** Once per component class (cached on the class or in an
`lru_cache`), compute a plan: per block, which fields, each with its
field kind (scalar, keystring, array, list, item table, child binding),
the reader to call, its dims and its converter. `structure_component`
and `_resolve_bindings` (`converter/ingress/structure.py`) then run the
plan instead of re-deriving it from type hints. Start by `lru_cache`ing
the pure helpers (`to_field_type`, `item_list_type`, `block_list_type`,
`repeating_array_key_type`) on their type arguments and measure. That
may be most of the win for little code. Do the full plan only if it
isn't.

Overlaps with the converter simplification (`pyphoenix-simplify-converter`
worktree), which reworks `structure.py`. Coordinate, or do it after.

**Tests:** smoke. **Bench:** standard tier, `test_load` (small models).

### 10. Columnar item tables

`from_rows` (`item.py`, ~line 1082) and `_read_ragged` (`item_table.py`,
~line 608) build one attrs instance per row: 106K `Disv.Cell2d` and 42K
`Sfr.StressPeriodData` in the large models, ~0.6 s cumulative (attrs
`__init__`, `__attrs_post_init__`, `read_row`, `_check_keyword`,
`to_union_arm`).

**Change.** Read ragged and item tables column-wise: one array per
fixed column, and offsets + a flat values array for each ragged one
(cell2d's `icvert`, which is how MF6 lays it out anyway). Union arms
become a tag column plus per-arm columns. Build row objects only on
access (`__getitem__` / iteration), and store columns back when rows
are assigned. Equality and the count check (`ncvert` vs. `len(icvert)`,
step 6) become vectorized: `np.diff(offsets) == ncvert`.

The biggest of these steps, touching the object model, not just
the loader. Needs a design pass first (how `item_table.py`'s public API
and the writer see it). Step 6 first, then measure what's left.

**Tests:** item-table unit tests, roundtrip snapshots, smoke. **Bench:**
biscqtg_disv, test028_sfr, large tier.

### 11. Further ideas, unmeasured

- **Parse cache.** Key (path, size, mtime), or a fast content hash, to
  the parsed blocks saved as `.npy`/pickle in a cache directory (not the
  shared temp dir, for the same reason as step 2). Reloading a simulation
  after editing one file re-parses only that file: the notebook loop.
  Needs invalidation on the flopy4 and grammar version, and a size
  threshold so small files don't pay the I/O.
- **Parallel parsing across files.** Each package file's parse is
  independent (bytes in, numpy and plain values out, picklable); only
  structuring needs dims. A process pool, or threads under free-threaded
  3.13t later, could parse a large model's files at once. Peterson's five
  big files are ~0.4 s of parse in series. Only worth it after 7-9, for
  large models, and the parse/structure boundary has to be clean.
- **Lazy external arrays** (still deferred, `loader-roadmap.md`). The
  profile puts numpy's `_load_from_filelike` at 0.34 s for biscqtg's
  external `.dat` arrays, which laziness would remove from load.
- **Period deduplication: checked, dropped for now.** Hashing period
  blocks found no repeats in the large models (`biscayne.riv`'s 100
  periods are all distinct). Revisit only if the corpus shows repeats.

## Housekeeping

- `load-baseline` branch and worktree (`~/dev/pyphoenix-load-baseline`)
  look superseded by #482. Confirm, then remove.
- The simplify-converter worktree is still at `fe5423c`; it's no longer
  something to coordinate with here.

## Not in this plan

- Lazy external arrays (`loader-roadmap.md`, "Deferred").
- Speeding up flopy3, or a flopy3 `lazy_io=True` benchmark column.
