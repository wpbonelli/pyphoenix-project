import argparse
from os import PathLike
from pathlib import Path
from pprint import pprint
from typing import Iterable, List, Literal, Optional

import pandas as pd
import toml
import yaml

from flopy4.mf6.io.spec import load as load_dfn

PROJ_ROOT = Path(__file__).parents[4]
SPEC_PATH = PROJ_ROOT / "flopy4" / "mf6" / "io" / "spec"
DFNS_PATH = SPEC_PATH / "dfn"
TOML_PATH = SPEC_PATH / "toml"
YAML_PATH = SPEC_PATH / "yaml"

DFNFormat = Literal["toml", "yaml"]


def collect_dfns(path: Path) -> List[Path]:
    if path.is_dir():
        return list(path.rglob("*.dfn"))
    elif path.suffix.lower() in [".dfn"]:
        if not path.is_file():
            raise FileNotFoundError(f"DFN file does not exist: {path}")
        return [path]


def load_spec(*dfn_paths: Iterable[PathLike]) -> dict:
    dfns = {}
    for p in dfn_paths:
        with open(p) as f:
            dfn = load_dfn(f)
        comp, sub = p.stem.split("-")
        if comp not in dfns:
            dfns[comp] = {}
        dfns[comp][sub] = dfn
    return dfns


def dump_spec(
    spec: dict,
    fmt: DFNFormat = "toml",
    path: Optional[Path] = None,
    combined: bool = False,
):
    def suffixed(p: Path):
        return p.with_suffix(f".{fmt}")

    def dump(s, p):
        if fmt == "toml":
            if p is None:
                print(toml.dumps(s))
            else:
                with open(suffixed(p), "w") as f:
                    toml.dump(s, f)
        elif fmt == "yaml":
            if p is None:
                print(yaml.dump(s, sort_keys=False))
            else:
                with open(suffixed(p), "w") as f:
                    yaml.dump(s, f, sort_keys=False)
        else:
            raise ValueError(f"Unsupported output format: {fmt}")

    if path is not None:
        if path.is_file():
            raise ValueError("Output path must be a directory")
        path.mkdir(exist_ok=True, parents=True)

    if combined:
        dump(spec, path)
    else:
        if not path.is_dir():
            raise ValueError(f"Output directory does not exist: {path}")
        specs = pd.json_normalize(spec, sep="-", max_level=1).to_dict(
            orient="records"
        )[0]
        for stem, s in specs.items():
            dump(s, suffixed(path / stem))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Convert DFN files to TOML files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Convert DFN files to equivalent TOML files. Can
also convert to YAML instead of TOML, or create
a single specification rather than one for each
input component.""",
    )
    parser.add_argument(
        "-d",
        "--dfn",
        required=False,
        default=DFNS_PATH,
        help="""
Path to a DFN file or directory containing DFN files.""",
    )
    parser.add_argument(
        "-o",
        "--out",
        required=False,
        default=Path.cwd(),
        help="""
Directory path to write converted files to. Pass '-' to print
to stdout.""",
    )
    parser.add_argument(
        "-f",
        "--format",
        required=False,
        default="toml",
        help="""
The format to convert definition files to. Value can be 'toml' 
or 'yaml'. Default is TOML.""",
    )
    parser.add_argument(
        "-c",
        "--combined",
        action="store_true",
        required=False,
        default=False,
        help="""
Generate a single combined specification rather than a separate 
specification for each input component.""",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        required=False,
        default=False,
        help="Whether to show verbose output.",
    )
    args = parser.parse_args()
    dfn = Path(args.dfn)
    out = None if args.out == "-" else Path(args.out)
    format = args.format
    combined = args.combined
    verbose = args.verbose

    # collect definition files
    dfns = collect_dfns(dfn)

    if verbose:
        print(f"Converting DFNs to {format.upper()}:")
        pprint(dfns)

    # load DFNs
    spec = load_spec(*dfns)

    # write converted output
    dump_spec(spec, format, out, combined)

    if verbose:
        print("Done converting DFNs.")
