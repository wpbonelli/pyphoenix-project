# Packages without a generated class are silently skipped

**Layer:** bindings (`_resolve_bindings`, `converter/ingress/structure.py`,
around line 509: `continue` when `get_ftype` finds no class).
**Fixed by the simplification:** no (codegen coverage).

Namefile rows for packages flopy4 doesn't generate yet are silently
dropped, so the model loads without them. Seen in `test051_uzfp2TS`:
`SFR6` and `UZF6` rows exist, but the loaded model has neither child.

Namefile ftype counts over the surveyed models include SFR6 31, MAW6 26,
UZF6 15, GNC6 10, HFB6 8, and the GWT packages. "Loads cleanly" in
`test_mf6_load_all_models.py` and "round-trips identically" in the survey
say nothing about these packages.

Not a converter bug, but it limits what Phase 0 can characterize (for
example the `test051_uzfp2TS` `TS6` repeat). Consider a warning on skip,
or recording skipped rows, so coverage is visible.

Also not modeled (seen in `test031_many_gwf`, 2026-09-23): exchanges.
There's no class for `GWF6-GWF6` (or any exchange type), so all 12
exchanges load as `sim.exchanges == {}` and the written `mfsim.nam` has an
empty `EXCHANGES` block. `Simulation` has no options fields either, so
`MEMORY_PRINT_OPTION SUMMARY` is dropped. The round-trip test can't see
either gap, because both are missing on both sides.
