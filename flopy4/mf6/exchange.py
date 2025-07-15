from abc import ABC
from pathlib import Path

from xattree import field, xattree

from flopy4.mf6.package import Package


@xattree
class Exchange(Package, ABC):
    # mypy doesn't understand that kw_only=True on the
    # Component means we can have required fields here
    exgtype: type = field()  # type: ignore
    exgfile: Path = field()  # type: ignore
    exgmnamea: str = field()
    exgmnameb: str = field()
