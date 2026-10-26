# Plan: input-load optimizations (what's left)

Written 2026-09-29 and trimmed 2026-10-26 to the open steps, against
`develop` at `fff532fe`. The full plan, with the measurements that
motivated it and the steps since done, is in this file's git history
(`archive/` holds the roadmap it was indexed from).

## Done on develop

- **Snapshot check** (old step 0): load snapshots (#481) and round-trip IO
  snapshots (#498).
- **Lazy imports** (old step 1, #445): flopy3 and xugrid are imported only
  by the adapters and output readers, not when loading a simulation.
- **Bulk tokens in `basic.lark`** (old steps 3 and 4): `NUMBERS` takes
  runs of numeric-only lines and `RECORDS` runs of lines with words, so
  neither inline arrays nor list rows cost a token per value.
- **Inline transformer** (part of old step 5): `get_basic_parser` passes
  the transformer to `Lark(...)`, so no tree is built.
- **One benchmark harness** (#482): `benchmarks/`, pytest-benchmark with
  tiers (`--bench-tier smoke|standard|large|full`), `bench-memory`
  (pytest-memray), `bench-profile` and `bench-report`. `docs/profile/` is
  gone.

The converter simplification (`docs/dev/converter-simplification-plan.md`,
branch `simplify-converter`) reworks `structure.py`, including the array
readers. Check its state before touching the same code.

## Ground rules

- Work in a new worktree under `~/dev/` (never `/tmp`), off `develop`.
- Run everything with `pixi run -e dev ...`. Verify with
  `pixi run -e dev smoke`, not the full suite, unless asked. Sign commits
  with the session's trailers. No pushes, PRs or GitHub actions unless the
  user asks.
- **One PR per step,** with `bench` numbers before and after
  (`bench-report --compare`) and clean load snapshots.

## 1. Harden the external-array reader

`_read_open_close_values` (`structure.py`) is fast but fails on any `#`
comment or stray text in an external file. Make it tolerant without losing
the bulk path:

```python
COMMENT = re.compile(r"[#!][^\n]*")
TABLE = str.maketrans({",": " ", ";": " ", "\t": " ", "'": None, '"': None, "d": "e", "D": "e"})
values = np.array(COMMENT.sub("", text).translate(TABLE).split(), dtype=dtype)
```

- Measured on VilhelmsenGF's external files: 0.062 s vs. 0.042 s at the
  time, still ~2x faster than flopy3's loop (0.134 s).
- **Check what MF6 accepts first.** The tolerated set above was a
  synthetic stress test, not MF6's spec. Only accept what MF6's own reader
  accepts; e.g. confirm whether `!` comments, `;` and quoted numbers are
  valid in external arrays, and drop what isn't.
- **Count check.** Take the expected length from dims. Too few values is
  an error ("expected N values for <field>, got M"); extra trailing values
  are ignored, matching MF6. The converter plan's "Later" list has the
  same issue for inline arrays ("Short arrays load"); fix both the same
  way.
- **Tests:** unit tests with comments, commas, `D` exponents, and too-few
  values, plus the load snapshots.

## 2. Cheaper Lark for whatever still goes through it

- **`cache=True`**, to save grammar analysis between processes. It matters
  mostly for cold start. The typed loader on `simplify-converter` already
  caches its built parsers on disk (B4); reuse that for the basic parser
  rather than adding a second mechanism.
- **`debug=True`** is still set on both parsers. Check whether it costs
  anything outside development, and drop it if so.

## 3. Lazy external arrays

Moved here from the loader roadmap. This changes what the object model
holds, not how fast parsing is. Revisit after the converter simplification
lands.

**The idea.** Read externally stored array data only when it's accessed,
not at load time. Today flopy4 reads every `OPEN/CLOSE` array eagerly. In
the load-baseline corpus that's 18 models and 12.6 MB of array files,
sometimes most of a model's bytes. Laziness would make those loads nearly
free, and users who touch only some arrays would never pay for the rest.

**Evidence it matters:**
- flopy3 already defers `OPEN/CLOSE` array reads until `get_data()`. That
  is one reason the benchmark has to materialize everything to compare
  fairly.
- Unlike flopy3, which re-reads the file on *every* access with no
  caching, flopy4 should read once and cache.

**Shape of it:**
- Binary `OPEN/CLOSE ... (BINARY)` arrays: memory-map the file
  (`np.memmap`, after the MF6 binary header) and wrap it as a lazily
  indexed array. Slices never touch the rest of the file.
- Text `OPEN/CLOSE` arrays: can't be indexed without parsing, so defer the
  whole read to first access. That's a `dask.delayed` read wrapped in a
  `dask.array`, or a small lazy array type. Read once, then cache.
- The object model holds these lazy arrays in place of numpy arrays. Shape
  and dtype are known at load from dims and the field type, so validation
  that needs only shape still works without reading.
- Writing: an unmodified lazy array can be written back as the same
  `OPEN/CLOSE` reference without being read (flopy3's `lazy_io` does the
  same). That's a round-trip win too.
- Inline arrays (inside the package file) stay eager: they have to be
  parsed to get past them anyway.

**Things to settle first:**
- Which consumers assume a concrete `np.ndarray`: converters, `to_xarray`,
  writers, validation.
- File-change semantics: what happens if the external file changes between
  load and first access? Probably document "read at first access" and move
  on.
- Benchmark impact: the "load + materialize" stage stays the fair
  comparison. A "load only" number will drop sharply and shouldn't be
  quoted alone.

**Xarray backend.** An `engine="mf6"` backend (`open_dataset` /
`open_datatree` → `load(...).to_xarray()`) is cheap given the existing
`to_xarray()` methods, but adds no speed and is a lossy view of input
files (options, records, bindings). If done, keep it a thin wrapper that
the reader never depends on. Lazy external arrays, built into the loader,
are the part of that idea worth pursuing, and a backend would get them for
free.

## 4. Weekly benchmark CI job

There's no benchmark workflow yet (`.github/workflows` has `ci.yml`,
`docs.yml` and `extended-win.yml`).

**Workflow:** `.github/workflows/benchmark.yml`.
- Triggers: `schedule` (weekly, e.g. Sunday night UTC);
  `workflow_dispatch` with an optional `ref` input; optionally a PR label
  such as `benchmark` for reader or converter changes. Never on every push.
- One runner type (`ubuntu-latest`) and one Python version. Cross-OS
  numbers aren't comparable, and the question is the trend on one
  platform.

**Steps:**
1. Checkout; setup pixi (`dev` environment, same versions as `ci.yml`).
2. `pixi run mf sync`, as in `ci.yml`, for the models registry.
3. Cache the downloaded models and DFNs across runs with `actions/cache`.
4. Install MF6 (`modflowpy/install-modflow-action`) if the output
   benchmarks need to run a simulation first.
5. For the `large`/`full` tiers: fetch `modflow6-largetestmodels` (cached)
   and set `MODFLOW6_LARGE_MODELS`. Check its size first.
6. Run the chosen tier with more rounds than locally, saving JSON
   (`--benchmark-json bench.json`).
7. Upload `bench.json` as an artifact (90-day retention), and append it
   to the long-term history (below).

**Noise.** GitHub-hosted runners are shared VMs whose CPU can change from
week to week.
- **Within a run:** 5 rounds plus a warm-up; compare the **min**, keep
  mean and stddev for diagnosis.
- **Between runs:**
  1. Make `flopy4 / flopy3` per group the headline trend metric. flopy3
     runs in the same job on the same machine, so the ratio is largely
     machine-independent.
  2. For precise comparisons (`workflow_dispatch`), benchmark a reference
     ref and `HEAD` in one job and report `HEAD / ref`.
- Record the CPU model in the saved JSON, so a hardware change can be told
  apart from a regression.
- If noise stays a problem, a self-hosted runner on fixed hardware is the
  real fix. That's a project decision.

**History and alerts.**
- [`benchmark-action/github-action-benchmark`](https://github.com/benchmark-action/github-action-benchmark)
  reads pytest-benchmark JSON (`tool: 'pytest'`; verify against its
  current docs), stores a history, renders trend charts, and can alert on
  a threshold.
- Docs deploy via `actions/deploy-pages`, so store the data on a dedicated
  branch (e.g. `bench-data`), not `gh-pages`.
- Alert generously (e.g. 30% slower), on the flopy4/flopy3 ratio as well
  as absolute time. The job never fails for a slowdown, only when a
  benchmark itself errors.

**Keeping benchmarks from rotting.** Add a cheap check to `ci.yml` that
runs the `smoke` tier once with `--benchmark-disable`, proving the code
still runs without timing anything.

## Not in this plan

- **The typed grammar's bulk tokens.** The typed loader on
  `simplify-converter` is 1.25x slower than basic (its
  `loader-comparison.md`); whether it gets the same `NUMBERS`/`RECORDS`
  treatment depends on whether it's kept.
- **Speeding up flopy3.**
- **A flopy3 `lazy_io=True` benchmark column.** Still an open decision.

## Done when

- Steps 1 and 2 are merged, each with before/after numbers, or recorded as
  measured and not worth it.
- The weekly job runs and keeps a history.
- Step 3 is either designed against the simplified converter or dropped.
