"""
Generate an MF6 Python module from definition files.

Usage (CLI)::

    python -m flopy4.mf6.utils.codegen.sync 
    python -m flopy4.mf6.utils.codegen.sync --release MODFLOW-ORG/modflow6@latest
    python -m flopy4.mf6.utils.codegen.sync --dfnpath /path/to/dfns
"""

import argparse
import logging
import sys
from os import PathLike
from pathlib import Path

from modflow_devtools.dfns import Dfns, RemoteDfnRegistry

from flopy4.mf6.utils.codegen import make_components

_PROJ_ROOT = Path(__file__).parents[4].expanduser().resolve()
_MF6_MODULE_ROOT = _PROJ_ROOT / "flopy4" / "mf6"
_MF6_REPO_OWNER = "MODFLOW-ORG"
_MF6_REPO_NAME = "modflow6"
_MF6_LATEST_RELEASE_ID = f"{_MF6_REPO_OWNER}/{_MF6_REPO_NAME}/@latest"

# DFN names that require special handling beyond simple package generation.
# These are skipped until their generation tier is implemented.
#
# nam files: model/simulation name files need special model-level handling.
# dis/disv: require DisBase + grid conversion methods (dis tier).
# tdis/ims: top-level hand-written files, not yet templated.
# *g / *a variants: gridded/array package variants, deferred.
#
# TODO (subpackage tier): detect `# flopy subpackage` DFN annotations and emit
# a typed child attrs field (e.g. ncf: Optional[Ncf]) alongside the existing path
# field; DisBase.write() already establishes the write pattern for NCF.
# utl-ts also needs period values referencing timeseries by name written as strings.
_SKIP = {
    # discretization tier (require DisBase + grid methods)
    "gwf-dis",
    "gwf-disv",
    "gwt-dis",
    "gwe-dis",
    "prt-dis",
    # time discretization (hand-written tdis.py)
    "sim-tdis",
    # hand-written: wkt field type override + Ncf.from_grid() factory.
    # TODO: move factory to NcfBase (utl/ncf_base.py) so codegen can own utl/ncf.py,
    # matching the DisBase pattern used for discretization packages.
    "utl-ncf",
}


def make(
    release: str = _MF6_LATEST_RELEASE_ID,
    dfndir: str | PathLike | None = None,
    outdir: str | PathLike = _MF6_MODULE_ROOT,
    developmode: bool = False,
) -> None:
    """Generate Python classes for MODFLOW 6 packages.

    Parameters
    ----------
    release : str, optional
        DFN source repository release ID (owner/name@tag). Defaults to
        'MODFLOW-ORG/modflow6@latest'.
    dfndir : str or pathlike, optional
        Path to a local directory of DFN files. Takes precedence
        over a release identifier when supplied.
    outdir : str or pathlike
        Root output directory.  Defaults to ``flopy4/mf6/``.
    developmode : bool, optional
        Include fields marked ``developmode`` in the DFN. Default False.
    """

    if dfndir is None:
        if registry := RemoteDfnRegistry.load_default().get(release, None) is None:
            registry = RemoteDfnRegistry(release_id=release)
        registry.sync(force=True)
        dfns = registry.spec
    else:
        dfns = Dfns.load(Path(dfndir).expanduser().resolve())

    make_components(
        dfns=dfns,
        outdir=Path(outdir).expanduser().resolve(),
        developmode=developmode,
    )


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Generate the flopy.mf6 module from definition files.",
    )
    parser.add_argument(
        "--release",
        default=f"{_MF6_LATEST_RELEASE_ID}",
        help="DFN source repository release ID (owner/name@tag)",
    )
    parser.add_argument(
        "--dfnpath",
        default=None,
        help="Path to a local directory of v1 .dfn files.",
    )
    parser.add_argument(
        "--outdir",
        default=str(_MF6_MODULE_ROOT),
        help="Root output directory (default: flopy4/mf6/ in the project).",
    )
    parser.add_argument(
        "--developmode",
        action="store_true",
        help="Include developmode fields.",
    )
    args = parser.parse_args()
    make(
        release=args.release,
        dfndir=args.dfnpath,
        outdir=args.outdir,
        developmode=args.developmode,
    )


if __name__ == "__main__":
    main()
