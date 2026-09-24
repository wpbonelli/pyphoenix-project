"""Simulation load benchmarks: flopy3 (`MFSimulation.load`) vs. flopy4
(`Simulation.load`, basic loader) over the real MF6 corpus.

Measures a full simulation load, the user-facing number. For flopy4's
parsers alone (basic vs. typed, per file), see `test_mf6_parse_benchmark.py`.

Opt-in -- skipped unless benchmarking is enabled::

    pixi run -e dev bench-load                              # run, autosave
    pixi run -e dev bench-load --benchmark-compare          # vs. last save

There's no ``flopy4-typed`` loader yet: typed parser output isn't wired
into structuring, so a full typed load doesn't exist. Add it to `LOADERS`
when it does.

Benchmarks (each parametrized by loader, ``flopy3`` or ``flopy4-basic``):

- `test_load` -- load only. Not like-for-like (see below).
- `test_load_materialize` -- load, then fetch and sum every array and
  list. **The fair comparison.**
- `test_load_materialize_largest` -- the same, per model, for the
  `N_LARGEST` models by input bytes, where per-model differences show most.
- `test_cold_start` -- a fresh interpreter per round: import, then load +
  materialize one mid-size model (`COLD_MODEL`). The child's own
  import/load/materialize split goes in `extra_info`.

What each loader reads, and when (flopy 3.11.0; see
docs/dev/load-benchmarks.md for the evidence):

- flopy3 ``MFSimulation.load(lazy_io=False, verify_data=False)``, with
  ``use_pandas=True`` (the default), parses internal data at load. It does
  *not* read ``OPEN/CLOSE`` array files: it stores the path and reads the
  file on every ``get_data()``, without caching. ``OPEN/CLOSE`` list files
  are read at load, but only because ``auto_set_sizes`` (on whenever
  ``lazy_io`` is off) calls ``get_data()`` to size ``maxbound``; they aren't
  cached either. It also loads packages flopy4 has no component for (DISU,
  MAW, SFR, UZF, exchanges, ...) and child files (TS, TAS, OBS, LAK tables).
- flopy4 ``Simulation.load`` reads everything it reads eagerly, but silently
  skips packages and child files it has no component for.

So the fair comparison is ``load + materialize``, with flopy3 restricted via
``load_only`` to the package types flopy4 loaded, on models where both then
open exactly the same set of files (`check`).

So the fair comparison is ``load + materialize``, with flopy3 restricted via
``load_only`` to the package types flopy4 loaded, on models where both then
open exactly the same set of files. That's checked once per session by
`check`, in a subprocess, since it installs a process-wide audit hook.

Pin the model set with ``--bench-load-manifest PATH``: the first run writes
the list, later runs use exactly that list and fail loudly if a listed model
no longer loads or no longer does equal work. `bench-load` pins it to
`load_benchmark_models.txt` next to this file.

**Layout.** This file is also a script, used for the subprocess steps::

    python test/mf6/test_mf6_load_benchmark.py check WS [WS ...]
    python test/mf6/test_mf6_load_benchmark.py cold flopy3|flopy4-basic WS [LOAD_ONLY ...]

So it's in three parts: (1) helpers that import only the standard library
at module level, (2) the script entry point, which exits before (3) the
pytest benchmarks import pytest and anything else. That keeps the
cold-start measurement honest: a child process times only its own
loader's imports, not pytest's (~0.1 s, measured).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# (1) Loaders, materializers, and work-equivalence checks. Standard library
# only at module level (see the module docstring); heavy imports stay inside
# the functions.
# ---------------------------------------------------------------------------

# flopy3 load options, fixed for every benchmark
FLOPY3_OPTIONS = {"verbosity_level": 0, "lazy_io": False, "verify_data": False, "use_pandas": True}


def silence() -> None:
    """Silence warnings and logging; printing isn't what's measured."""
    import logging
    import warnings

    warnings.simplefilter("ignore")
    logging.disable(logging.CRITICAL)


def load_only_for(dfn_names) -> list[str]:
    """flopy3 `load_only` entries for the flopy4 components that loaded.

    Array-based rch/evt (``rcha``) and grid-based (``chdg``) packages are
    distinct flopy4 components but share one flopy3 ftype (``rch``, ``chd``).
    flopy3 always loads the discretization, the TDIS and namefiles."""
    out = set()
    for name in dfn_names:
        component, _, sub = name.partition("-")
        if component == "exg":
            out.add(f"{sub[:3]}6-{sub[3:]}6")
            continue
        out.add(sub)
        if sub in ("rcha", "evta") or (len(sub) == 4 and sub.endswith("g")):
            out.add(sub[:-1])
    return sorted(out)


def load_flopy3(ws: Path, load_only: list[str]):
    import flopy

    return flopy.mf6.MFSimulation.load(sim_ws=str(ws), load_only=load_only, **FLOPY3_OPTIONS)


def load_flopy4(ws: Path):
    from flopy4.mf6.simulation import Simulation

    return Simulation.load(ws / "mfsim.nam")


def load_flopy4_recording(ws: Path):
    """`load_flopy4`, also returning the DFN names of the packages it loaded."""
    from unittest import mock

    from flopy4.mf6.package import Package

    names: set[str] = set()
    original = Package.load.__func__  # type: ignore[attr-defined]

    def wrapper(cls, path, dims=None, name=None):
        names.add(cls.dfn_name)
        return original(cls, path, dims=dims, name=name)

    with mock.patch.object(Package, "load", classmethod(wrapper)):
        sim = load_flopy4(ws)
    return sim, sorted(names)


def touch(x) -> int:
    """Sum `x`'s numeric content, returning the number of values touched."""
    import numbers

    import numpy as np
    import pandas as pd

    if x is None or isinstance(x, (str, bytes, bool)):
        return 0
    if isinstance(x, numbers.Number):
        return 1
    if isinstance(x, np.ndarray):
        if x.dtype.names:
            return sum(touch(x[n]) for n in x.dtype.names)
        if x.dtype.kind in "biuf":
            x.sum()
            return x.size
        if x.dtype.kind == "O":
            return sum(touch(v) for v in x.ravel())
        return 0
    if isinstance(x, pd.DataFrame):
        num = x.select_dtypes("number")
        num.to_numpy().sum()
        objs = [c for c in x.columns if x[c].dtype == object]
        return num.size + sum(touch(v) for c in objs for v in x[c])
    if hasattr(x, "values") and hasattr(x, "dims"):  # xarray
        return touch(x.values)
    if isinstance(x, dict):
        return sum(touch(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return sum(touch(v) for v in x)
    return 0


def materialize_flopy3(sim) -> int:
    """Fetch every array and list dataset of every loaded package, and sum it.

    `MFArray`/`MFTransientArray`/`MFList`/`MFTransientList` via `get_data()`;
    pandas-backed lists via `get_dataframe()`, the native form (`get_data()`
    would add a DataFrame -> recarray conversion). Scalars aren't touched;
    they're always parsed at load. This is what reads ``OPEN/CLOSE`` arrays.
    """
    from flopy.mf6.data.mfdataarray import MFArray
    from flopy.mf6.data.mfdatalist import MFList
    from flopy.mf6.data.mfdataplist import MFPandasList

    packages = list(sim.sim_package_list)
    for name in sim.model_names:
        packages.extend(sim.get_model(name).packagelist)
    n = 0
    for package in packages:
        for block in package.blocks.values():
            for dataset in block.datasets.values():
                if isinstance(dataset, MFPandasList):
                    n += touch(dataset.get_dataframe())
                elif isinstance(dataset, (MFArray, MFList)):
                    n += touch(dataset.get_data())
    return n


def materialize_flopy4(sim) -> int:
    """Walk the component tree and sum every numeric value held.

    flopy4 holds everything in memory after load, so this reads no files;
    it's here so both loaders' ``load + materialize`` touch their data."""
    import attrs

    from flopy4.mf6.component import Component

    seen: set[int] = set()
    skip = ("_parent", "parent", "workspace", "filename")

    def walk(obj) -> int:
        if id(obj) in seen:
            return 0
        seen.add(id(obj))
        items = dict(vars(obj)) if hasattr(obj, "__dict__") else {}
        if attrs.has(type(obj)):  # slotted records have no __dict__
            for f in attrs.fields(type(obj)):
                if f.name not in items and hasattr(obj, f.name):
                    items[f.name] = getattr(obj, f.name)
        n = sum(value(v) for k, v in items.items() if k not in skip)
        if isinstance(obj, Component):
            n += sum(walk(child) for child in obj._children.values())
        return n

    def value(v) -> int:
        if isinstance(v, Component) or (attrs.has(type(v)) and not isinstance(v, type)):
            return walk(v)
        if isinstance(v, dict):
            return sum(value(x) for x in v.values())
        if isinstance(v, (list, tuple)):
            return sum(value(x) for x in v)
        return touch(v)

    return walk(sim)


def check(ws: Path) -> dict:
    """Load and materialize `ws` with both loaders, recording the files each
    opens under `ws` (via an audit hook). Equal work means equal file sets.

    Needs `_audit` installed, a process-wide hook: run it in a subprocess
    (`main`), never in the benchmark process."""
    wsr = os.path.realpath(ws)

    def tracked(fn):
        global _opened
        _opened = []
        try:
            out = fn()
        finally:
            opened, _opened = _opened, None
        return out, {os.path.relpath(p, wsr) for p in opened if p.startswith(wsr + os.sep)}

    result: dict = {"ws": str(ws)}
    try:
        (sim4, dfns), f4 = tracked(lambda: load_flopy4_recording(ws))
        _, f4_mat = tracked(lambda: materialize_flopy4(sim4))
        load_only = load_only_for(dfns)
        sim3, f3 = tracked(lambda: load_flopy3(ws, load_only))
        _, f3_mat = tracked(lambda: materialize_flopy3(sim3))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
        return result
    all3, all4 = f3 | f3_mat, f4 | f4_mat
    result.update(
        load_only=load_only,
        only_flopy3=sorted(all3 - all4),
        only_flopy4=sorted(all4 - all3),
        flopy3_at_materialize=sorted(f3_mat - f3),
        flopy4_at_materialize=sorted(f4_mat - f4),
        n_bytes=sum(os.path.getsize(os.path.join(wsr, f)) for f in all4),
    )
    result["equal"] = not result["only_flopy3"] and not result["only_flopy4"]
    return result


_opened: list[str] | None = None


def _audit(event, args):
    if event == "open" and _opened is not None and isinstance(args[0], (str, bytes, os.PathLike)):
        _opened.append(os.path.realpath(os.fsdecode(args[0])))


def cold(loader: str, ws: Path, load_only: list[str]) -> dict:
    """Import `loader` and load + materialize `ws`, timing each step. Meant
    to run first thing in a fresh interpreter."""
    t0 = time.perf_counter()
    if loader == "flopy3":
        import flopy  # noqa: F401

        t1 = time.perf_counter()
        sim = load_flopy3(ws, load_only)
        t2 = time.perf_counter()
        materialize_flopy3(sim)
    else:
        import flopy4.mf6.simulation  # noqa: F401

        t1 = time.perf_counter()
        sim = load_flopy4(ws)
        t2 = time.perf_counter()
        materialize_flopy4(sim)
    t3 = time.perf_counter()
    return {"import": t1 - t0, "load": t2 - t1, "materialize": t3 - t2}


def main(argv: list[str]) -> None:
    command, *args = argv
    if command == "check":
        silence()
        sys.addaudithook(_audit)
        for ws in args:
            print(json.dumps(check(Path(ws))), flush=True)
    elif command == "cold":
        loader, ws, *load_only = args
        silence()
        print(json.dumps(cold(loader, Path(ws), load_only)), flush=True)
    else:
        raise SystemExit(f"unknown command: {command}")


# ---------------------------------------------------------------------------
# (2) Script entry point: exit before the pytest section's imports.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main(sys.argv[1:])
    raise SystemExit

# ---------------------------------------------------------------------------
# (3) Benchmarks.
# ---------------------------------------------------------------------------

import pytest  # noqa: E402
from modflow_devtools.models import copy_to  # noqa: E402

from .test_mf6_load_all_models import KNOWN_PASSING  # noqa: E402

ROUNDS = 3
COLD_ROUNDS = 5
N_LARGEST = 5
# a mid-size DISV model (~0.55 MB, 5 packages + an OPEN/CLOSE array);
# the corpus median is ~12 KB, so "mid" is relative to the models that
# take long enough to measure
COLD_MODEL = "mf6/test/test050_circle_island"
HELPER = Path(__file__)


@pytest.fixture(scope="module", autouse=True)
def _require_benchmarking(request):
    config = request.config
    if config.getoption("benchmark_disable") and not config.getoption("benchmark_enable"):
        pytest.skip("benchmarks disabled; pass --benchmark-enable")


class Model(NamedTuple):
    name: str
    ws: Path
    load_only: list[str]
    n_bytes: int


class LoadCorpus(NamedTuple):
    models: list[Model]
    excluded: dict[str, str]  # model -> reason

    @property
    def info(self) -> dict:
        import flopy

        return {
            "n_models": len(self.models),
            "n_bytes": sum(m.n_bytes for m in self.models),
            "n_excluded": len(self.excluded),
            "flopy_version": flopy.__version__,
            "flopy3_options": FLOPY3_OPTIONS,
        }


def _exclusion_reason(result: dict) -> str:
    if "error" in result:
        return result["error"]
    return f"only flopy3 opens {result['only_flopy3']}; only flopy4 opens {result['only_flopy4']}"


@pytest.fixture(scope="module")
def load_corpus(request, tmp_path_factory) -> LoadCorpus:
    manifest: Path | None = request.config.getoption("bench_load_manifest")
    pinned = manifest.read_text().split() if manifest and manifest.exists() else None
    names = pinned if pinned is not None else sorted(KNOWN_PASSING)

    workspaces = {}
    for name in names:
        ws = copy_to(tmp_path_factory.mktemp("bench-load"), name, verbose=False)
        if ws is not None and (ws / "mfsim.nam").exists():
            workspaces[str(ws)] = (name, ws)
    missing = set(names) - {name for name, _ in workspaces.values()}
    if pinned is not None and missing:
        pytest.fail(f"pinned models not found: {sorted(missing)}")

    # a fresh interpreter, so the audit hook never touches the timed process
    proc = subprocess.run(
        [sys.executable, str(HELPER), "check", *workspaces],
        capture_output=True,
        text=True,
        check=True,
    )
    results = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    assert len(results) == len(workspaces), proc.stderr[-2000:]

    models, excluded = [], {}
    for result in results:
        name, ws = workspaces[result["ws"]]
        if result.get("equal"):
            models.append(Model(name, ws, result["load_only"], result["n_bytes"]))
        else:
            excluded[name] = _exclusion_reason(result)
    if pinned is not None and excluded:
        pytest.fail(f"pinned models no longer load with equal work: {excluded}")
    assert models, "empty load benchmark corpus"
    if pinned is None and manifest is not None:
        manifest.write_text("\n".join(m.name for m in models) + "\n")
    return LoadCorpus(models, excluded)


def _load_flopy3(models: list[Model]) -> None:
    for m in models:
        load_flopy3(m.ws, m.load_only)


def _load_flopy4(models: list[Model]) -> None:
    for m in models:
        load_flopy4(m.ws)


def _load_materialize_flopy3(models: list[Model]) -> None:
    for m in models:
        materialize_flopy3(load_flopy3(m.ws, m.load_only))


def _load_materialize_flopy4(models: list[Model]) -> None:
    for m in models:
        materialize_flopy4(load_flopy4(m.ws))


# benchmark id -> (load, load + materialize), over a list of models
LOADERS = {
    "flopy3": (_load_flopy3, _load_materialize_flopy3),
    "flopy4-basic": (_load_flopy4, _load_materialize_flopy4),
}


@pytest.fixture
def quiet():
    import logging
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        logging.disable(logging.CRITICAL)
        try:
            yield
        finally:
            logging.disable(logging.NOTSET)


@pytest.mark.slow
@pytest.mark.parametrize("loader", LOADERS)
def test_load(benchmark, load_corpus, quiet, loader):
    """Load only. Not like-for-like: flopy3 defers ``OPEN/CLOSE`` arrays."""
    benchmark.group = "load"
    benchmark.extra_info.update(load_corpus.info)
    benchmark.pedantic(
        LOADERS[loader][0], args=(load_corpus.models,), rounds=ROUNDS, iterations=1, warmup_rounds=1
    )


@pytest.mark.slow
@pytest.mark.parametrize("loader", LOADERS)
def test_load_materialize(benchmark, load_corpus, quiet, loader):
    """Load, then fetch and sum every array and list: the fair comparison."""
    benchmark.group = "load-materialize"
    benchmark.extra_info.update(load_corpus.info)
    benchmark.pedantic(
        LOADERS[loader][1], args=(load_corpus.models,), rounds=ROUNDS, iterations=1, warmup_rounds=1
    )


@pytest.mark.slow
@pytest.mark.parametrize("loader", LOADERS)
@pytest.mark.parametrize("rank", range(1, N_LARGEST + 1), ids=lambda r: f"largest{r}")
def test_load_materialize_largest(benchmark, load_corpus, quiet, rank, loader):
    """Load + materialize of each of the largest corpus models (by input
    bytes), where per-model differences show most."""
    model = sorted(load_corpus.models, key=lambda m: -m.n_bytes)[rank - 1]
    benchmark.group = f"load-materialize-largest{rank}"
    benchmark.extra_info.update(model=model.name, n_bytes=model.n_bytes)
    benchmark.pedantic(
        LOADERS[loader][1], args=([model],), rounds=ROUNDS, iterations=1, warmup_rounds=1
    )


@pytest.mark.slow
@pytest.mark.parametrize("loader", LOADERS)
def test_cold_start(benchmark, load_corpus, loader):
    """Wall time of a fresh interpreter that imports `loader`, then loads
    and materializes `COLD_MODEL`. The child's own import/load/materialize
    split (last round) goes in `extra_info`."""
    model = next((m for m in load_corpus.models if m.name == COLD_MODEL), None)
    if model is None:
        pytest.fail(f"{COLD_MODEL} not in the load corpus")
    cmd = [sys.executable, str(HELPER), "cold", loader, str(model.ws)]
    if loader == "flopy3":
        cmd += model.load_only
    split: dict = {}

    def run():
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        split.update(json.loads(proc.stdout.strip().splitlines()[-1]))

    benchmark.group = "load-cold"
    benchmark.extra_info.update(model=model.name, n_bytes=model.n_bytes)
    benchmark.pedantic(run, rounds=COLD_ROUNDS, iterations=1)
    benchmark.extra_info.update(split)
