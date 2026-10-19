# Single-name AUXILIARY is lost

**FIXED** on branch `roundtrip-fixes` (`25611a5`).

**Layer:** ingress Pass 1 (`converter/ingress/structure.py:736-741`),
egress (`converter/egress/unstructure.py:235`).
**Fixed by the simplification:** yes, by the Phase 2 inline-array value
parser.

`AUXILIARY CONCENTRATION` (one name) loads as the string
`'CONCENTRATION'`, not `['CONCENTRATION']`. The list branch is gated on
`shape` metadata, but `auxiliary` is declared `Optional[list[str]]` with
no `shape` (checked on Chd, Wel, Rch), so only a row with more than two
tokens becomes a list. Egress's
`f.name == "auxiliary" and isinstance(field_value, list)` branch then
skips it, so the option is dropped on write and reloads as `None`. Any
`aux` columns in the stress period data then no longer have names.

Affected (7): test001a_Tharmonic_extlist, test005_advgw_tidal,
test201_gwtbuy-henryCHD, test202_gwtbuy-henryCHDm, test203_gwtbuy-henryGHB,
test204_gwtbuy-henryGHBm, test205_gwtbuy-henrytidal.

Fix direction: `auxiliary` is an inline array, so it's always a list of
`row[1:]`. Decide list-ness from the declared type (`list[...]`) or DFN
shape, not from `shape` metadata alone.
