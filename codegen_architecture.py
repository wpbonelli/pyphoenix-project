"""
Architecture for code generation with minimal generated code.

Demonstrates how to keep validation logic in base classes while
generated classes are just field declarations.

Key insight: Pydantic's model_validator can inspect model_fields
and apply generic logic based on metadata.
"""

from __future__ import annotations

from typing import Annotated, Any

import numpy as np
import xarray as xr
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator


# ============================================================================
# Shared validation logic (lives in base library, NOT generated)
# ============================================================================


def structure_array_generic(
    value: Any,
    field_name: str,
    dims: tuple[str, ...],
    dtype: np.dtype,
    context: dict[str, Any],
) -> NDArray | xr.DataArray:
    """
    Generic array structuring logic.

    This is your structure_array function - lives in ONE place,
    not duplicated in generated code.

    Args:
        value: Input value (scalar, array, dict, etc.)
        field_name: Name of the field
        dims: Expected dimensions (e.g., ('nodes',))
        dtype: Expected dtype
        context: Validation context with dimension values

    Returns:
        Structured array
    """
    dim_values = context.get("dims", {})

    # Already structured - validate and return
    if isinstance(value, (np.ndarray, xr.DataArray)):
        expected_shape = tuple(dim_values.get(d, d) for d in dims)
        # Validation logic...
        return value

    # Scalar - broadcast to full array
    if isinstance(value, (int, float, np.number)):
        shape = tuple(dim_values[d] for d in dims)
        return np.full(shape, value, dtype=dtype)

    # Dict format - structured input
    if isinstance(value, dict):
        shape = tuple(dim_values[d] for d in dims)
        arr = np.zeros(shape, dtype=dtype)
        for idx, val in value.items():
            arr[idx] = val
        return arr

    # ... your full structure_array logic here (500 lines)
    # But it only exists ONCE in the base library

    return value


# ============================================================================
# Field factory for generated code (minimal, just metadata)
# ============================================================================


def MF6Array(
    dims: tuple[str, ...],
    block: str,
    netcdf: bool = False,
    longname: str | None = None,
    dtype: type | None = None,
):
    """
    Field factory for MF6 arrays.

    This is what generated code uses - just metadata, no validation logic.
    """
    return Field(
        json_schema_extra={
            "mf6_type": "array",  # ← Marker for base class validator
            "dims": dims,
            "block": block,
            "netcdf": netcdf,
            "longname": longname,
            "dtype": dtype,
        }
    )


def MF6Field(
    block: str,
    longname: str | None = None,
    **kwargs,
):
    """Field factory for MF6 scalars."""
    return Field(
        json_schema_extra={
            "mf6_type": "scalar",
            "block": block,
            "longname": longname,
        },
        **kwargs,
    )


# ============================================================================
# Base class with generic validation (NOT generated)
# ============================================================================


class Package(BaseModel):
    """
    Base class for all MF6 packages.

    Contains ALL validation logic - generated classes inherit this
    and get validation for free.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,  # Implicit validation!
    )

    parent: Any = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def structure_all_arrays(cls, data: dict, info: ValidationInfo) -> dict:
        """
        Generic array structuring for ALL array fields.

        This runs once per class initialization, inspects model_fields,
        and structures any field marked as mf6_type='array'.

        NO GENERATED CODE NEEDED - all classes get this for free!
        """
        # Get dimension context (from parent or explicit)
        context = info.context or {}
        dim_values = context.get("dims", {})

        # Inspect model_fields to find arrays
        for field_name, field_info in cls.model_fields.items():
            # Skip if not in input data
            if field_name not in data:
                continue

            # Get metadata
            metadata = field_info.json_schema_extra or {}

            # Only process array fields
            if metadata.get("mf6_type") != "array":
                continue

            # Extract array metadata
            dims = tuple(metadata.get("dims", []))
            dtype_val = metadata.get("dtype", np.float64)

            # Convert dtype if needed
            if isinstance(dtype_val, type):
                dtype = np.dtype(dtype_val)
            else:
                dtype = dtype_val

            # Structure the array using generic logic
            data[field_name] = structure_array_generic(
                value=data[field_name],
                field_name=field_name,
                dims=dims,
                dtype=dtype,
                context=context,
            )

        return data

    def to_dataset(self) -> xr.Dataset:
        """Convert to xarray Dataset (can also be generic)."""
        # Generic implementation that works for all packages
        arrays = {}
        attrs = {}

        for field_name, field_info in self.model_fields.items():
            metadata = field_info.json_schema_extra or {}
            value = getattr(self, field_name)

            if metadata.get("mf6_type") == "array":
                arrays[field_name] = value
            elif metadata.get("mf6_type") == "scalar":
                attrs[field_name] = value

        return xr.Dataset(arrays, attrs=attrs)


# ============================================================================
# GENERATED CODE - Minimal, just field declarations!
# ============================================================================


class Dis(Package):
    """
    GENERATED from DIS.dfn

    Notice: NO validation code, NO converters, just field declarations!
    All validation inherited from Package base class.
    """

    # Dimension fields (scalars)
    nlay: Annotated[int, MF6Field(block="dimensions", longname="number of layers")]
    nrow: Annotated[int, MF6Field(block="dimensions", longname="number of rows")]
    ncol: Annotated[int, MF6Field(block="dimensions", longname="number of columns")]

    # Array fields - just metadata, validation is automatic!
    delr: Annotated[
        NDArray[np.float64],
        MF6Array(
            dims=("ncol",),
            block="griddata",
            netcdf=True,
            longname="spacing along a row",
            dtype=np.float64,
        ),
    ]

    delc: Annotated[
        NDArray[np.float64],
        MF6Array(
            dims=("nrow",),
            block="griddata",
            netcdf=True,
            longname="spacing along a column",
            dtype=np.float64,
        ),
    ]

    top: Annotated[
        NDArray[np.float64],
        MF6Array(
            dims=("nrow", "ncol"),
            block="griddata",
            netcdf=True,
            longname="model top elevation",
            dtype=np.float64,
        ),
    ]

    botm: Annotated[
        NDArray[np.float64],
        MF6Array(
            dims=("nlay", "nrow", "ncol"),
            block="griddata",
            netcdf=True,
            longname="model bottom elevation",
            dtype=np.float64,
        ),
    ]

    def get_dimensions(self) -> dict[str, int]:
        """Provide dimensions (could also be generic on base class)."""
        return {
            "nlay": self.nlay,
            "nrow": self.nrow,
            "ncol": self.ncol,
            "nodes": self.nlay * self.nrow * self.ncol,
        }


class Npf(Package):
    """
    GENERATED from NPF.dfn

    Again: NO validation code! Just field declarations.
    """

    save_flows: Annotated[
        bool, MF6Field(block="options", longname="save flows")
    ] = False

    icelltype: Annotated[
        NDArray[np.int64],
        MF6Array(
            dims=("nodes",),
            block="griddata",
            netcdf=True,
            longname="cell type",
            dtype=np.int64,
        ),
    ]

    k: Annotated[
        NDArray[np.float64],
        MF6Array(
            dims=("nodes",),
            block="griddata",
            netcdf=True,
            longname="hydraulic conductivity",
            dtype=np.float64,
        ),
    ]


# ============================================================================
# Demonstration
# ============================================================================


def demo():
    """Show that generated classes work with zero validation code."""

    print("=" * 70)
    print("Code Generation Architecture Demo")
    print("=" * 70)

    # Create DIS with dimension context
    print("\n1. Creating DIS (generated class, zero validation code)...")
    dis = Dis.model_validate(
        {
            "nlay": 3,
            "nrow": 10,
            "ncol": 10,
            "delr": 100.0,  # Scalar - automatically broadcast
            "delc": 100.0,
            "top": np.ones((10, 10)) * 10,
            "botm": np.ones((3, 10, 10)) * -10,
        },
        context={"dims": {"nlay": 3, "nrow": 10, "ncol": 10}},
    )
    print(f"   delr shape: {dis.delr.shape}")
    print(f"   Validation logic: IN BASE CLASS, not generated code!")

    # Create NPF
    print("\n2. Creating NPF (generated class, zero validation code)...")
    npf = Npf.model_validate(
        {
            "save_flows": False,
            "icelltype": 1,  # Scalar - automatically broadcast to 300 nodes
            "k": 10.0,
        },
        context={"dims": dis.get_dimensions()},
    )
    print(f"   k shape: {npf.k.shape}")
    print(f"   k dtype: {npf.k.dtype}")
    print(f"   Validation logic: IN BASE CLASS, not generated code!")

    # Show generated code is minimal
    print("\n3. Generated code analysis...")
    print(f"   Dis class lines: ~60 (just field declarations)")
    print(f"   Npf class lines: ~40 (just field declarations)")
    print(f"   Validation code in Dis: 0 lines")
    print(f"   Validation code in Npf: 0 lines")
    print(f"   ALL validation: Package.structure_all_arrays() - 1 method!")

    print("\n" + "=" * 70)
    print("Key Points:")
    print("  - Generic validation logic in Package base class")
    print("  - Generated classes are JUST field declarations")
    print("  - No duplication of structure_array logic")
    print("  - All array fields validated automatically via metadata")
    print("=" * 70)


if __name__ == "__main__":
    demo()
