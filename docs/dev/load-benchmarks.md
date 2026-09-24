# Simulation load benchmarks: flopy3 vs. flopy4

A baseline for simulation *input* loading, for later loader changes to be
measured against. Measured 2026-09-24 at commit `5bae03a`, on an Intel Core
Ultra 7 155H (WSL2, CPython 3.11.16), with flopy 3.11.0.

## What's compared, and at which level

| level | flopy3 | flopy4 basic | flopy4 typed |
|---|---|---|---|
| full simulation load | `MFSimulation.load` | `Simulation.load` | **not possible yet** |
| parse stage (`loads`) | n/a | yes | yes |

Typed `loads` output isn't wired into `structure.py`, so there's no full typed
load to time. The typed loader appears here at the parse stage only. It gets a
column in the first row once it's wired in.

## The loaders don't do the same work by default

This was settled by recording every file each loader opens (a `sys` audit hook
on `open`), both during load and during a later "materialize" pass. It was
cross-checked against flopy3's source.

### flopy3

`MFSimulation.load(verbosity_level=0, lazy_io=False, verify_data=False)`, with
`use_pandas=True` (the default).

- **Internal data** (inline arrays and lists) is parsed at load.
- **`OPEN/CLOSE` arrays are not read at load.** `_load_layer` hands the
  control line to `process_open_close_line`, which stores the file path, not
  the data. `get_data()` reads the file on every call, and nothing caches it.
  In the benchmark corpus, 18 models have 56 array files (12.6 MB of the
  31.8 MB total) that flopy3 opens only when their data is accessed.
- **`OPEN/CLOSE` lists are read at load, but only as a side effect.**
  `lazy_io=False` leaves `auto_set_sizes` on. `MFPackage.load` then calls
  `_update_size_defs`, which calls `get_data()` on every list to size
  `maxbound`. That reads the external file, converts the DataFrame to a
  recarray, and throws both away. Access reads the file again.
  - `lazy_io=True` turns `auto_set_sizes` off, and then flopy3 reads no
    external list files at load. It isn't benchmarked.
  - `lazy_io` doesn't otherwise make array reading lazier. Arrays are
    deferred either way.
- **flopy3 loads more than flopy4 does.** It reads packages flopy4 has no
  component for (DISU, MAW, SFR, UZF, HFB, GNC, GWF-GWF exchanges, ...) and
  child files (TS, TAS, OBS, LAK tables).

### flopy4

`Simulation.load(path)`, the basic loader.

- Everything it reads, it reads at load, `OPEN/CLOSE` arrays and lists
  included (`_read_open_close_values`, `_resolve_open_close_rows`). No model
  opened any file during materialize.
- It silently skips packages and child files it has no component for. It
  records a `ts_file`/`obs_file` path without opening it.

### Equalizing the work

- flopy3 gets `load_only`, set to the package types flopy4 actually loaded
  for that model (recorded by wrapping `Package.load`). flopy3 always loads
  the discretization, TDIS and namefiles regardless.
- Two stages are timed. `sim-load` is load only. `sim-load-materialize` is
  load, then touch everything. Only the second is like-for-like, because
  flopy3 defers `OPEN/CLOSE` arrays.
- "Materialize" means:
  - **flopy3:** for every package in `sim.sim_package_list` and every model's
    `packagelist`, and every dataset in every block:
    - `get_dataframe()` for pandas-backed lists (their native form;
      `get_data()` would add a recarray conversion);
    - `get_data()` for `MFArray`, `MFTransientArray`, `MFList` and
      `MFTransientList`.

    Then sum every numeric array, column or field. Scalars aren't touched,
    since they're always parsed at load.
  - **flopy4:** walk the component tree (attrs fields and `__dict__`, into
    records, dicts and lists), summing every numeric value.
- A model is in the corpus only if both loaders, after load and materialize,
  opened **exactly the same set of files**. That check runs once per session,
  in a subprocess, so the audit hook never runs in the timed process.
- As a spot check that flopy4 doesn't read a file and then drop its data:
  across the 165 corpus models, every one of the 1,874 non-transient griddata
  arrays that flopy3 holds data for is non-`None` on the matching flopy4
  package. (This used a scratch script and isn't part of the benchmark.) The
  one model where flopy4 did drop griddata, `test006_gwf3_disv_ext`, is
  excluded by the file check anyway.

The two loaders still keep data differently. For example, flopy4 sometimes
keeps a `CONSTANT` array as a scalar where flopy3's `get_data()` builds the
full array. They also hold lists differently: a DataFrame in flopy3, lists of
attrs records in flopy4. These differences are part of what's timed.

## Corpus

This is the 239 `KNOWN_PASSING` models (`test_mf6_load_all_models.py`) minus
the 74 where the file sets differ. That leaves **165 models, 31.8 MB** of input
files. All 239 load without error under both loaders, so every exclusion is
about unequal work, not failures. The list is pinned in
`test/mf6/load_bench_models.txt`.

| excluded | reason |
|---|---|
| 44 | flopy3 reads TS/TAS and/or OBS child files that flopy4 doesn't load (24 with TS/TAS, 20 OBS only) |
| 17 | DISU models: flopy4 has no DISU component, and flopy3 always loads the discretization |
| 10 | flopy3 reads LAK table files (`utl-laktab` children), mostly alongside TS/OBS |
| 1 | `test005_advgw_tidal`: TS/OBS files, plus an `OPEN/CLOSE` file referenced from an OBS file |
| 1 | `test006_gwf3_disv_ext`: DISV `DIMENSIONS` is `OPEN/CLOSE`, so flopy4 can't size the grid. It leaves `top`/`botm`/`idomain` as `None` and doesn't read `CELL2D` |
| 1 | `test051_uzfp2_openclose`: flopy4 reads OC per-period `OPEN/CLOSE` files, but flopy3 never opens them, even on access |

## Results

These are warm runs, in-process, after one untimed warm-up round. Figures are
the minimum of 3 rounds, from `pixi run -e dev bench-load` with the pinned
manifest. An earlier run agreed within 2% on the corpus figures and within
5% on the per-model ones.

### Whole corpus (165 models, 31.8 MB)

| stage | flopy3 | flopy4 basic | flopy3 / flopy4 |
|---|---|---|---|
| `sim-load` (not like-for-like) | 15.56 s | 13.72 s | 1.13 |
| **`sim-load-materialize`** | **17.01 s** | **14.44 s** | **1.18** |

The corpus total is misleading on its own. One model,
`test205_gwtbuy-henrytidal`, accounts for ~10 s of flopy3's 17 s.

A scratch script timed each model separately: warm, load + materialize, best
of 3. It showed:

- The totals were 16.10 s for flopy3 and 13.26 s for flopy4. Without
  henrytidal, they're **6.24 s and 9.99 s**, so flopy4 is slower on the rest.
- flopy4 is faster on 127 of the 165 models, which are mostly small ones.
  - For the 127 models under 50 ms with both loaders, the median is 20.4 ms
    for flopy3 and 8.2 ms for flopy4. flopy3 has more fixed overhead per
    model.
  - The median per-model ratio (flopy4 / flopy3) is 0.44. The 10th
    percentile is 0.31 and the 90th is 3.09.

### Largest models (load + materialize)

| model | input | flopy3 | flopy4 | flopy4 / flopy3 |
|---|---|---|---|---|
| `test019_VilhelmsenGF` | 10.8 MB | 0.392 s | 0.141 s | 0.36 |
| `test120_mv_disv_xt3d` | 3.8 MB | 0.556 s | 2.736 s | 4.92 |
| `test205_gwtbuy-henrytidal` | 3.1 MB | 9.969 s | 3.354 s | 0.34 |
| `test016_Keating_dev` | 1.5 MB | 0.385 s | 0.675 s | 1.75 |
| `test016_Keating` | 1.5 MB | 0.382 s | 0.666 s | 1.74 |

Each model shows a different regime:

- **VilhelmsenGF.** Almost all of its bytes are `OPEN/CLOSE` array files.
  flopy4 reads these with `np.array(text.split())`, entirely in C. flopy3
  reads them on access, through its own per-layer reader.
- **mv_disv_xt3d and Keating.** Large *internal* arrays. flopy4's Lark path
  costs per token in pure Python (see
  [Why the typed loader isn't faster (yet)](typed-grammar-remarks.md#why-the-typed-loader-isnt-faster-yet)).
  flopy3 reads the same data faster.
- **henrytidal.** It has ~970 stress periods of GHB and DRN list data (1,939
  period blocks), and flopy3 pays a fixed pandas cost per block. cProfile
  shows two main costs:
  - `_read_text_data`, with `_decrement_id_fields` inside it;
  - `_update_size_defs` (`auto_set_sizes`), which converts each block's
    DataFrame to a recarray just to count rows. This was about 30% of
    flopy3's profiled load.

### Cold start

Each round runs a fresh interpreter that imports the loader, then loads and
materializes `test050_circle_island` (0.55 MB DISV). The measurement is
wall time, minimum of 5 rounds. The breakdown columns come from inside the
child process, in its last round.

| | wall | import | load | materialize |
|---|---|---|---|---|
| flopy3 | 0.94 s | 0.54 s | 0.24 s | 0.05 s |
| flopy4 basic | 2.41 s | 1.52 s | 0.56 s | 0.03 s |

- flopy4's import dominates its cold start. `python -X importtime` puts
  ~0.64 s of it in importing flopy3 itself (`flopy.discretization`, for
  grids) and ~0.45 s in `xugrid`.
- flopy3's DFN structure build happens on first load, inside its "load"
  column.

### Parse stage, basic vs. typed

These come from the existing reader benchmark (`pixi run -e dev bench`), run in
the same session. The corpus is 2,149 package files (21.6 MB) that both
grammars parse, and figures are the minimum of 3 rounds.

This is **parse stage only**. It's a different corpus and a different unit of
work from the full loads above, so don't compare the two tables' times
directly.

| stage | basic | typed | typed / basic |
|---|---|---|---|
| parse | 12.62 s | 13.28 s | 1.05 |
| parse + transform (`loads`) | 14.37 s | 17.81 s | 1.24 |
| typed grammar build (30 components, once per process) | | 1.74 s | |

## Not measured yet

- **A full typed load**, which doesn't exist yet (see above).
- **The 74 excluded models.** flopy4 skips DISU, TS/OBS and other child
  files. Once it loads them, those models can join the corpus, but that
  changes the pinned set, so it needs a fresh baseline.
- **flopy3 with `lazy_io=True`.** That turns off `auto_set_sizes`, which
  would likely help henrytidal-style inputs a lot.

## Reproducing

```shell
# load benchmarks (opt-in; ~6.5 min); pinned to test/mf6/load_bench_models.txt
pixi run -e dev bench-load
pixi run -e dev bench-load --benchmark-compare      # vs. the last saved run

# re-derive the model set: point the manifest option at a new path.
# Later options win, so this overrides the task's own --bench-load-manifest
pixi run -e dev bench-load --bench-load-manifest /path/to/new-models.txt

# the file-set check or the cold start by hand, for one or more workspaces
pixi run -e dev python test/mf6/load_bench.py check WS [WS ...]
pixi run -e dev python test/mf6/load_bench.py cold flopy4 WS

# parse-stage basic vs. typed (~4 min)
pixi run -e dev bench
```

Saved runs go to `.benchmarks/`, which is git-ignored. Each benchmark's
`extra_info` records:

- `n_models`, `n_bytes`, `n_excluded`, the flopy version and the flopy3
  load options;
- the model name, for the per-model and cold-start groups.

The per-model distribution and the griddata coverage check came from scratch
scripts. Both are easy to reconstruct from `load_bench.py`:

- the distribution loops over the manifest, timing
  `materialize_*(load_*(ws))` best-of-3 per loader;
- the coverage check matches packages by filename and compares
  `MFArray.has_data()` with the flopy4 attribute.
