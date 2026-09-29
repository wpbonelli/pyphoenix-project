# Handoff: input-loader benchmarks and optimization

Written 2026-09-29 to pick this work up on another machine. Start here.

> **This `plans/` directory is temporary.** It lives on `load-baseline` only
> so it travels with the branch. **Drop the commit that adds it before
> opening the PR** (`git rebase -i` and drop it, or move `plans/` to a
> separate branch). The PR itself should be tests and docs only.

## What's in `plans/`

| file | what | status |
|---|---|---|
| `HANDOFF.md` | this file: state, next steps, the PR draft | current |
| `loader-roadmap.md` | index of all the loader work, and how it's staged | current |
| `optimization-plan.md` | basic-loader speed-ups, unifying benchmark infra, weekly CI job | not started |
| `typed-loader-wiring-plan.md` | wiring the typed loader in next to the basic one, behind a switch | not started |
| `load-baseline-plan.md` | the plan that produced this branch's load benchmark | done |
| `typed-grammar-trailing-remarks.md` | the original trailing-remarks question | answered, in `docs/dev/typed-grammar-remarks.md` |

These were written as untracked files in the original checkout's root.
They refer to each other by bare filename, which still works here. Paths
like `~/dev/pyphoenix-typed-remarks` and the Claude scratchpad are specific
to the original machine.

## State of the branches (fork: `wpbonelli/pyphoenix-project`)

| branch | contents | state |
|---|---|---|
| `load-baseline` | parse + load benchmarks, both analysis docs, this `plans/` commit | pushed; based on `develop` @ `fe5423c`, **5 commits behind `develop`** |
| `typed-remarks` | earlier subset of `load-baseline`, with old benchmark names | superseded; don't PR it |
| `typed-no-remarks` | experiment: trailing-remark support removed from the typed grammar | reference only, never merge |

`develop` has moved: #369 (round-trip test), #370 (number parsing: both
grammars changed), #371, #372 (lossless float writing), #373 (trailing text
in `structure.py`). A trial rebase of `load-baseline` onto `develop` @
`840b952` was **clean**, and lint, format, codespell and smoke all passed
(1,395 passed, benchmarks skipped). The trial branch wasn't pushed, so
redo the rebase on the new machine.

## Next steps to merge `load-baseline`

1. **Set up.** Clone the fork, `git checkout load-baseline`, then
   `pixi install -e dev`. Always run through `pixi run -e dev ...`, never
   `uv run`. For local DFNs, clone `modflow6` next to this repo
   (`../modflow6`); the `dfn_path` test fixture finds it. Otherwise it
   downloads modflow6 `develop`.
2. **Rebase onto `develop`**: `git fetch upstream && git rebase
   upstream/develop`. Expect no conflicts. Then check with
   `pixi run -e dev ruff check`, `ruff format --check`, `codespell`, and
   `pixi run -e dev smoke`.
3. **Run the benchmarks** (`pixi run -e dev bench`, ~10 min). This matters
   after #370/#373:
   - `bench-load` fails loudly if any of the 165 pinned models no longer
     loads, or no longer does equal work. If so, re-derive the list with
     `--bench-load-manifest /tmp/new.txt`, look at what changed, and update
     `test/mf6/load_benchmark_models.txt` and the doc's exclusion table.
   - Note whether the numbers moved vs. the recorded baseline. The basic
     transformer now decides "is this a number?" for every token (#370).
4. **Docs fixes:**
   - Add `dev/load-benchmarks` and `dev/typed-grammar-remarks` to
     `docs/_toc.yml` under the other `dev/` entries (or use
     `scripts/update_ghpages.py --add-dev-doc`). Neither is listed now, so
     they wouldn't be published.
   - Label the recorded numbers as measured at `fe5423c`, before #370.
     Replace "measured at commit `5bae03a`" in `load-benchmarks.md`: that
     hash is a fork commit and won't exist upstream after a squash merge.
     Add the post-rebase numbers from step 3 alongside, or instead.
   - `typed-grammar-remarks.md`, "Branches": point at the fork explicitly
     (e.g. `wpbonelli/pyphoenix-project`, branch `typed-no-remarks`). The
     remark-failure counts (47 → 404) were also measured before #370;
     say so.
5. **Drop the `plans/` commit** (see the top of this file). Keep these
   files somewhere else.
6. Force-push `load-baseline` to the fork, and open the PR with the
   description below.

## Draft PR description

**Title:** Input load benchmarks: flopy3 vs. flopy4, basic vs. typed parser

Adds opt-in benchmarks for loading MF6 input, a recorded baseline, and two
analysis docs. Tests and docs only; no production code changes.

**Benchmarks** (pytest-benchmark, skipped unless `--benchmark-enable`;
skipped under `smoke`)

- `pixi run -e dev bench-parse` (`test/mf6/test_mf6_parse_benchmark.py`):
  flopy4's basic vs. typed parser over ~2,150 corpus package files: parse
  only, parse + transform, and typed grammar build.
  `--bench-parse-manifest` pins the file set, for comparing grammar
  variants on identical input.
- `pixi run -e dev bench-load` (`test/mf6/test_mf6_load_benchmark.py`):
  full `Simulation.load`, flopy3 vs. flopy4 (basic), over 165 pinned
  corpus models (`load_benchmark_models.txt`). Four benchmarks:
  - load only;
  - load + read all data (the fair comparison);
  - the five largest models;
  - cold start in a fresh interpreter.
- `pixi run -e dev bench` runs both (~10 min). Results save to
  `.benchmarks/` (git-ignored); compare runs with `--benchmark-compare`.

**Making the comparison fair.** flopy3 defers reading `OPEN/CLOSE` arrays
until access, and loads packages flopy4 doesn't support yet. So flopy3 is
restricted with `load_only` to what flopy4 loads, and a model is only
benchmarked if both loaders open exactly the same files, verified with an
audit hook in a subprocess. 74 of the 239 known-loadable models are
excluded on those grounds, with reasons listed in the doc.

**Findings** (`docs/dev/load-benchmarks.md`,
`docs/dev/typed-grammar-remarks.md`)

- **Overall:** flopy4 loads the corpus in 14.4 s vs. flopy3's 17.0 s, but
  one model accounts for ~10 s of flopy3's time. flopy4 has less fixed
  overhead and wins on 127 of 165 models.
- **Inline arrays:** flopy4 is 2–5× slower. Lark does Python work per
  token, while flopy3's reader works per line.
- **External arrays:** flopy4 is ~3× faster, because it reads each file in
  one numpy pass, while flopy3 loops per line and re-reads the file on
  every access.
- **Cold start:** flopy4 is 2.5× slower, mostly from imports (flopy3 for
  grids, xugrid).
- **Basic vs. typed parser:** the typed parser isn't faster (~1.07× parse,
  ~1.25× with transform). Moving logic into the grammar doesn't pay off in
  a pure-Python parser. The headroom is parsing bulk numeric data in C.
- **Trailing free-text remarks** can't be dropped from the typed grammar:
  357 more corpus files fail without them. They cost nothing measurable at
  parse time.

*(Update the numbers from step 3 above, and note which were measured
before #370.)*

**Follow-ups (not in this PR):** lazy imports, bulk numeric parsing for
inline arrays and lists, a weekly CI benchmark job, and unifying this with
the `docs/profile/` scripts.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

## After the merge

Follow `loader-roadmap.md`. In short:

- **Performance** (`optimization-plan.md`), for the basic loader, in
  parallel with the typed work:
  - re-baseline on `develop`;
  - value-snapshot check;
  - lazy imports;
  - tolerant external-array reader;
  - bulk numeric-run token (the big one: estimated ~2× faster than flopy3
    overall);
  - then lists with words, and cheaper Lark.
- **Benchmark infra** (`optimization-plan.md`, "Benchmark
  infrastructure"): the weekly CI job first, then unify
  `test/mf6/test_mf6_*_benchmark.py` and `docs/profile/` under
  `test/bench/` with pytest-benchmark.
- **Typed loader** (`typed-loader-wiring-plan.md`):
  - switch + parity test;
  - schema from generated classes;
  - output representation;
  - then structuring, after the converter simplification.
  - Re-check which typed-transformer bugs #370 already fixed: the
    `START_DATE_TIME` truncation likely is.

## Ground rules carried over (from the original machine's assistant memory)

- Worktrees go in a persistent location (e.g. `~/dev/`), never `/tmp`.
- Use `pixi run -e dev`, never `uv run`.
- Verify with `pixi run -e dev smoke`. Full test or benchmark runs happen
  when the user asks, not unprompted.
- No GitHub actions (issues, PRs, comments, pushes) without an explicit
  ask.
- Sign assisted commits with a `Co-Authored-By:` trailer.
- Justify generality (recursion, new IR layers) with verified schema or
  spec facts.
