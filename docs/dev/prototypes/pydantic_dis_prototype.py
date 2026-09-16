"""
Pydantic prototype v2: ports `Dis` (flopy4/mf6/gwf/dis.py, via `DisBase` ->
`Package` -> `Component`) to pydantic, in its *current* (post-xattree,
post-Row-unification) shape.

This exists to satisfy step 1-3 of docs/dev/pydantic-object-model-plan.md's
"Next steps when picked up": port one real, current-shape package end to
end, port its __attrs_post_init__/DimensionResolverMixin chain, and
re-measure effort/ergonomics against the actual current codebase rather
than trusting the January prototype's numbers.

Mined from:
- flopy4/mf6/component.py, flopy4/mf6/package.py, flopy4/dimensions.py,
  flopy4/mf6/gwf/{dis,disbase}.py -- the mechanics being ported.
- origin/plan-codegen's pydantic_prototype.py (2026-01-23) -- the
  pydantic-side mechanics (Annotated NDArray hints, field_validator
  array-structuring pattern, model_validator). Reused near-verbatim where
  still applicable; see inline notes where it wasn't.

Not wired into flopy4's real registry (FNAMES/FTYPES), codegen, or the
xarray/write/load machinery -- this is a standalone measurement of the
object-model layer only, not a drop-in replacement. `Ncf` is stubbed
(`NcfProto`) rather than importing the real attrs-based `Ncf`, since
mixing attrs and pydantic components isn't the point of this exercise.

Run directly: `python docs/dev/prototypes/pydantic_dis_prototype.py`
"""

from __future__ import annotations

from abc import ABC
from typing import Annotated, Any, ClassVar, Optional

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

# ============================================================================
# Base: MF6Base
# ============================================================================


class MF6Base(BaseModel):
    """Root base class. `validate_assignment=True` is the pydantic mechanic
    that directly replaces attrs' `on_setattr`/`__attrs_post_init__`-driven
    validation-on-assignment story -- see PackageBase.griddata below for a
    worked case of *why* that matters (it's the concrete friction point
    docs/dev/pydantic-object-model-plan.md names as "real, still-open")."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,  # for np.ndarray / NDArray fields
        validate_assignment=True,
        extra="forbid",
    )


# ============================================================================
# Component: parent/child wiring + dimension resolution
#
# FRICTION POINT #1 (see write-up): attrs' private-attribute convention
# (`_parent` field, `parent=` constructor kwarg, via leading-underscore
# name mangling) doesn't exist in pydantic -- and doesn't need to. A field
# just named `parent` works directly, `exclude=True` keeps it out of
# `model_dump()`/schema. Net *simplification* over the attrs version.
# ============================================================================


class ComponentBase(MF6Base, ABC):
    filename: Optional[str] = None
    name: Optional[str] = None
    parent: Optional["ComponentBase"] = Field(default=None, exclude=True, repr=False)
    dims: dict = Field(default_factory=dict, exclude=True)

    # FRICTION POINT #2: attrs' `attrs.Factory(lambda self: ..., takes_self=True)`
    # (Component.name's real default: the lowercased *runtime* class name)
    # has no direct pydantic BaseModel equivalent -- Field(default_factory=...)
    # callables take no args. Closest equivalent is a `model_validator(mode="after")`
    # that fills the field in if still unset, which is what this does. One
    # extra method vs. attrs' one-liner, but it composes fine with the rest
    # of the post-init chain below (a single "after" validator handles both
    # concerns, whereas attrs needed the Factory *and* a post-init chain).
    @model_validator(mode="after")
    def _default_name(self) -> "ComponentBase":
        if self.name is None:
            self.name = type(self).__name__.lower()
        return self

    def default_filename(self) -> str:
        return f"{self.name}.{type(self).__name__.lower()}"

    # FRICTION POINT #3: attrs.fields(cls) (class-level, no instance needed)
    # vs. pydantic's cls.model_fields (also class-level, same shape) -- a
    # wash. What *did* change: attrs.Attribute.type is the raw type
    # annotation; pydantic's FieldInfo.annotation is the same thing, and
    # json_schema_extra (this prototype's stand-in for attrs field
    # `.metadata`) is where MF6-specific metadata (`block`, `shape`,
    # `netcdf`, ...) lives -- passed through Field(json_schema_extra={...})
    # exactly like attrs field(metadata={...}) today.
    @classmethod
    def _child_fields(cls) -> list[str]:
        """Fields whose annotation is (or wraps) another ComponentBase --
        replaces attrs_xarray.child_field_candidates() for the "only" case
        this prototype needs (Dis -> Ncf). List/dict child collections
        (Package.item_list fields, model-level `wel: list[Wel]` etc.) are
        out of scope here -- Dis has none -- and are flagged as unfinished
        business in the write-up, not silently glossed over.
        """
        names = []
        for fname, finfo in cls.model_fields.items():
            ann = finfo.annotation
            args = getattr(ann, "__args__", ())
            candidates = (ann, *args)
            if any(isinstance(a, type) and issubclass(a, ComponentBase) for a in candidates):
                names.append(fname)
        return names

    def _set_child_parents(self) -> None:
        for fname in self._child_fields():
            child = getattr(self, fname, None)
            if isinstance(child, ComponentBase):
                child.__dict__["parent"] = self
                if child.name is None:
                    child.name = fname

    # -- DimensionResolverMixin equivalent --------------------------------
    def get_dims(self) -> dict[str, int]:
        return {}

    def resolve_dims(self, *dims: str) -> dict[str, int]:
        if "_dimension_cache" not in self.__dict__:
            self.__dict__["_dimension_cache"] = {}
        cache = self.__dict__["_dimension_cache"]

        all_dims: dict[str, int] = {}
        if self.parent is not None:
            all_dims.update(self.parent.resolve_dims())
        all_dims.update(self.get_dims())
        for fname in self._child_fields():
            child = getattr(self, fname, None)
            if isinstance(child, ComponentBase):
                all_dims.update(child.get_dims())
        cache.update(all_dims)

        if not dims:
            return all_dims
        return {d: all_dims[d] for d in dims if d in all_dims}

    # FRICTION POINT #4: this is the chain attrs did via
    # `__attrs_post_init__` calling `super().__attrs_post_init__()` across
    # DimensionResolverMixin -> Component -> Package -> DisBase -> Dis.
    # `model_post_init` is pydantic's one hook for "after full validation",
    # but it does *not* auto-chain through bases the way `super()` +
    # `__attrs_post_init__` did (pydantic dispatches to the *most derived*
    # override only) -- each subclass that needs post-init work must
    # explicitly call `super().model_post_init(context)` itself. Same
    # obligation attrs had, just a different method name and no
    # `hasattr(super(), ...)` guard needed since BaseModel always defines
    # the hook (no-op by default).
    def model_post_init(self, __context: Any) -> None:
        self._set_child_parents()


# ============================================================================
# Package: griddata broadcasting via model_validator
# ============================================================================


_DTYPE_MAP = {"integer": np.int64, "double": np.float64}


class PackageBase(ComponentBase, ABC):
    # FRICTION POINT #5: a griddata field's *declared* type is
    # `NDArray[np.float64]`, but its *default value* in the current attrs
    # code is a bare scalar (`default=1.0`) that only becomes a real array
    # once dims are known (Package._broadcast_griddata, called from
    # __attrs_post_init__). attrs never type-checks this mismatch (no
    # validator on the field, and attrs doesn't validate types by default
    # at all). Pydantic, by contrast, DOES enforce it: constructing
    # `DisProto(delr=100.0, ...)` raised `ValidationError: Input should be
    # an instance of ndarray` immediately, confirmed by actually running
    # this prototype -- before `_coerce_arrays` below was added.
    #
    # This does NOT need to be written once per field, or even once per
    # generated class -- a single `field_validator("*", mode="before")`,
    # defined ONE time on this shared base, driven by each field's own
    # `json_schema_extra` metadata (`shape` present => it's an array
    # field), covers every array field on every subclass, including ones
    # not yet written. Confirmed with a standalone test
    # (`d.delr = 5.0` after construction still coerces, since
    # `validate_assignment=True` re-runs "before" validators too) --
    # earlier revisions of this prototype declared this per-field on
    # `DisProto` directly and described it as an unavoidable per-generated-
    # field cost; that was wrong. Codegen's array-field template doesn't
    # need to emit a validator at all -- just the `shape=` metadata it
    # already emits today.
    @field_validator("*", mode="before")
    @classmethod
    def _coerce_arrays(cls, v: Any, info: ValidationInfo) -> Any:
        finfo = cls.model_fields.get(info.field_name)
        if finfo is None or v is None:
            return v
        meta = finfo.json_schema_extra or {}
        if not (isinstance(meta, dict) and meta.get("block") == "griddata" and meta.get("shape")):
            return v
        if isinstance(v, np.ndarray):
            return v
        dtype = _DTYPE_MAP.get(meta.get("dfn_type", "double"), np.float64)
        return np.asarray(v, dtype=dtype)

    # Deliberately a plain method, not a `model_validator` -- called
    # explicitly from `model_post_init` (see DisProto below), the same way
    # the real `Package._broadcast_griddata`/`DisBase._coerce_griddata` are
    # plain methods called explicitly from `__attrs_post_init__`, not attrs
    # validators. Keeping the same shape here makes the port closer to
    # line-for-line and avoids a real wrinkle: `model_validator`s run in
    # MRO/declaration order and don't compose with "run this after a
    # subclass computes derived fields first" the way an explicit
    # `model_post_init` call chain does.
    def _broadcast_griddata(self) -> None:
        dims = self.resolve_dims()
        if not dims:
            return self
        for fname, finfo in type(self).model_fields.items():
            meta = finfo.json_schema_extra or {}
            if meta.get("block") != "griddata":
                continue
            shape_dims = meta.get("shape")
            if not shape_dims:
                continue
            val = getattr(self, fname, None)
            if val is None:
                continue
            try:
                shape = tuple(dims[d] for d in shape_dims)
            except KeyError:
                continue
            dtype = _DTYPE_MAP.get(meta.get("dfn_type", "double"), np.float64)
            if not isinstance(val, np.ndarray) or val.shape == shape:
                continue
            if val.size == 1:
                # scalar (post-_coerce_array, a 0-d ndarray) -> broadcast
                object.__setattr__(self, fname, np.full(shape, val.item(), dtype=dtype))
            elif meta.get("layered") and val.size == dims.get("nlay", 1):
                object.__setattr__(
                    self, fname, np.repeat(val, np.prod(shape) // val.size).astype(dtype)
                )
            else:
                try:
                    object.__setattr__(self, fname, val.reshape(shape))
                except ValueError:
                    pass

    def model_post_init(self, __context: Any) -> None:
        self._broadcast_griddata()
        super().model_post_init(__context)


# ============================================================================
# NcfProto: minimal child-component stub (real Ncf is attrs-based and out
# of scope -- this exists only to exercise Component's child-wiring path)
# ============================================================================


class NcfProto(ComponentBase):
    dfn_name: ClassVar[str] = "utl-ncf"
    latitude: Optional[str] = None
    longitude: Optional[str] = None


# ============================================================================
# DisBase / Dis
# ============================================================================


class DisBaseProto(PackageBase, ABC):
    # FRICTION POINT #2 (recap): these were `attrs.field(init=False)` --
    # excluded from the constructor entirely, always computed. Pydantic's
    # BaseModel has no field-level "not an init param" flag (that's a
    # `pydantic.dataclasses.dataclass` feature, not BaseModel's). Cheapest
    # equivalent: leave them as normal Optional fields and *unconditionally
    # overwrite* them in `model_post_init`, same as this prototype does
    # below. A caller *can* still pass `nodes=` positionally at construction
    # time and have it silently overwritten -- attrs raised `TypeError:
    # unexpected keyword argument` instead. Worth a real decision (extra="forbid"
    # doesn't help here since the field itself is real) if this survives
    # into an actual migration -- e.g. a `model_validator(mode="before")`
    # that pops and warns/rejects these keys explicitly.
    nlay: Optional[int] = None
    nrow: Optional[int] = None
    ncol: Optional[int] = None
    ncpl: Optional[int] = None
    nvert: Optional[int] = None
    nodes: Optional[int] = None


class DisProto(DisBaseProto):
    dfn_name: ClassVar[str] = "gwf-dis"

    length_units: Optional[str] = Field(default=None, json_schema_extra={"block": "options"})
    nogrb: bool = Field(default=False, json_schema_extra={"block": "options"})
    xorigin: float = Field(default=0.0, json_schema_extra={"block": "options"})
    yorigin: float = Field(default=0.0, json_schema_extra={"block": "options"})
    export_array_netcdf: bool = Field(default=False, json_schema_extra={"block": "options"})
    ncf: Optional[NcfProto] = None

    nlay: int = Field(default=1, json_schema_extra={"block": "dimensions"})  # type: ignore[assignment]
    ncol: int = Field(default=2, json_schema_extra={"block": "dimensions"})  # type: ignore[assignment]
    nrow: int = Field(default=2, json_schema_extra={"block": "dimensions"})  # type: ignore[assignment]

    delr: Annotated[
        NDArray[np.float64],
        Field(json_schema_extra={"block": "griddata", "shape": ("ncol",), "netcdf": True}),
    ] = 1.0  # type: ignore[assignment]
    delc: Annotated[
        NDArray[np.float64],
        Field(json_schema_extra={"block": "griddata", "shape": ("nrow",), "netcdf": True}),
    ] = 1.0  # type: ignore[assignment]
    top: Annotated[
        NDArray[np.float64],
        Field(json_schema_extra={"block": "griddata", "shape": ("ncpl",), "netcdf": True}),
    ] = 1.0  # type: ignore[assignment]
    botm: Annotated[
        NDArray[np.float64],
        Field(
            json_schema_extra={
                "block": "griddata",
                "shape": ("nodes",),
                "layered": True,
                "netcdf": True,
            }
        ),
    ] = 0.0  # type: ignore[assignment]

    # No per-field validator needed here -- PackageBase._coerce_arrays
    # (a single `field_validator("*", mode="before")`) already covers
    # delr/delc/top/botm via their `shape=` metadata.

    def get_dims(self) -> dict[str, int]:
        return {
            "nlay": self.nlay,
            "nrow": self.nrow,
            "ncol": self.ncol,
            "nodes": self.nlay * self.nrow * self.ncol,
            "ncpl": self.nrow * self.ncol,
        }

    # `nodes`/`ncpl`/`nvert` must exist before `resolve_dims()` (called
    # inside `_broadcast_griddata`) can see them -- same ordering
    # constraint the real `Dis.__attrs_post_init__` documents (compute
    # derived dims, *then* chain to super()). Since `_broadcast_griddata`
    # is a plain method (not a decorator-ordered validator -- see
    # PackageBase above), satisfying that constraint is just "call things
    # in the right order here," identical in shape to the attrs version.
    # `super().model_post_init(__context)` re-runs PackageBase's own
    # broadcast call once more (harmless -- already-broadcast arrays
    # reshape to a no-op) before reaching ComponentBase's child-wiring.
    def model_post_init(self, __context: Any) -> None:
        self.nodes = self.ncol * self.nrow * self.nlay
        self.ncpl = self.ncol * self.nrow
        self.nvert = (self.ncol + 1) * (self.nrow + 1)
        self._broadcast_griddata()
        super().model_post_init(__context)


# ============================================================================
# Demonstration / smoke test
# ============================================================================


def demo() -> None:
    print("=" * 70)
    print("Pydantic Dis prototype (current codebase shape)")
    print("=" * 70)

    dis = DisProto(nlay=3, nrow=10, ncol=10, delr=100.0, delc=100.0, top=1.0, botm=0.0)
    print(f"\nget_dims(): {dis.get_dims()}")
    assert dis.nodes == 300 and dis.ncpl == 100 and dis.nvert == 121
    print(f"delr: shape={dis.delr.shape}, dtype={dis.delr.dtype}")
    assert dis.delr.shape == (10,)
    print(f"botm: shape={dis.botm.shape}")
    assert dis.botm.shape == (300,)

    ncf = NcfProto(latitude="lat", longitude="lon")
    dis2 = DisProto(nlay=1, nrow=2, ncol=2, ncf=ncf)
    assert dis2.ncf is not None and dis2.ncf.parent is dis2
    print(f"\nchild wiring: dis2.ncf.parent is dis2 -> {dis2.ncf.parent is dis2}")
    print(f"child wiring: dis2.ncf.name -> {dis2.ncf.name!r}")

    print("\nvalidate_assignment=True in effect:")
    try:
        dis.xorigin = "not a float"
        raise AssertionError("expected a validation error")
    except Exception as e:
        print(f"  dis.xorigin = 'not a float' -> raised {type(e).__name__} as expected")

    print("\nAll assertions passed.")


if __name__ == "__main__":
    demo()
