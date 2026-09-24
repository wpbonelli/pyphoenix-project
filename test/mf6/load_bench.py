"""Loaders, materializers and work-equivalence checks for the simulation
load benchmark (`test_mf6_load_benchmark.py`). Not a test module.

Also runnable as a script, so the file-access check and the cold-start
measurement run in a fresh interpreter, away from the benchmark process::

    python test/mf6/load_bench.py check WS [WS ...]    # JSON line per workspace
    python test/mf6/load_bench.py cold flopy3|flopy4 WS

Only the standard library is imported at module level. That keeps the
cold-start measurement honest: the script times its own imports.

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
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# flopy3 load options, fixed for every benchmark
FLOPY3_OPTIONS = {"verbosity_level": 0, "lazy_io": False, "verify_data": False, "use_pandas": True}


def quiet() -> None:
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
        quiet()
        sys.addaudithook(_audit)
        for ws in args:
            print(json.dumps(check(Path(ws))), flush=True)
    elif command == "cold":
        loader, ws, *load_only = args
        quiet()
        print(json.dumps(cold(loader, Path(ws), load_only)), flush=True)
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main(sys.argv[1:])
