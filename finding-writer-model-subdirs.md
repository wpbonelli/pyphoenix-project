# Writer doesn't create model subdirectories

**FIXED** on branch `roundtrip-fixes` (`a08c862`).

**Layer:** writer (`_write_mf6`, `flopy4/mf6/__init__.py:85`, opens
`component.path` directly).
**Fixed by the simplification:** no.

`test031_many_gwf` keeps each model's files in a subdirectory
(`m1_1/model.dis`, ...). After loading and writing to a new workspace:

    FileNotFoundError: .../b/m1_1/model.dis

Fix direction: `component.path.parent.mkdir(parents=True, exist_ok=True)`
before opening the file. Also check that relative paths in namefile
bindings are written relative to the new workspace.
