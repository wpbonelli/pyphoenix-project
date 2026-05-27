import argparse

from flopy4.mf6.codec.reader.grammar import make_grammars
from flopy4.mf6.utils.codegen.dfn2py import make_components, _MF6_MODULE_ROOT, _MF6_LATEST_RELEASE_ID


def main():
    parser = argparse.ArgumentParser(
        description="Sync the flopy.mf6 module to a version of MF6, by default the latest."
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
    make_grammars(args.dfndir, args.outdir)
    make_components(
        release=args.release,
        dfndir=args.dfnpath,
        outdir=args.outdir,
        developmode=args.developmode,
    )


if __name__ == "__main__":
    main()
