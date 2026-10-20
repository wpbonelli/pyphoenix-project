"""The typed loader: a component from its typed parse (its own grammar's,
see ``flopy4.mf6.codec.reader.loads_typed``), without the basic loader's
converter or the DFNs. Kept beside the basic loader to compare the two
(see docs/dev/converter-simplification-plan.md, Track B).

Components it doesn't cover yet are read by the basic loader instead, so
a load with ``loader="typed"`` always works, and grows faster as more
components are covered."""

from typing import Any

from flopy4.mf6.load_context import LoadContext

# The components the typed loader reads, by DFN name.
COVERED: frozenset[str] = frozenset()


def covers(cls: type) -> bool:
    """Whether the typed loader reads ``cls``'s files."""
    return getattr(cls, "dfn_name", None) in COVERED


def structure_typed(
    parsed: dict, cls: type, *, context: LoadContext, name: str | None = None
) -> Any:
    """A ``cls`` from its file's typed parse."""
    raise NotImplementedError(f"The typed loader doesn't read {cls.__name__} yet.")
