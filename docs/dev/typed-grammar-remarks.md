# Trailing remarks in the typed grammar

Findings from 2026-09-23. The question was whether the typed grammar
(`flopy4/mf6/codec/reader/grammar/typed.lark` plus the generated per-component
grammars) needs to keep supporting trailing remarks, and what supporting them
costs.

## Background

MF6 input lets most lines end with free text after their real tokens, and it
isn't `#`-prefixed: `CONSTANT 100.0 DELR`. `basic.lark` never models this. Every
line is `item*`, and the structuring code downstream ignores the extra tokens.
`typed.lark` is field-shaped, so it threads an optional `[_remark]` through 7
rule sites (array control lines, data rows, scalar/record/union/file fields,
block headers). That forces:

- significant newlines, to bound the remark;
- a `COMMA` terminal that remarks can't contain, so a remark never swallows a
  comma-joined data run;
- a low-priority `_REMARK` terminal.

It also causes one known corpus gap: 2 `gwf-npf` files where a remark contains
a reserved word (e.g. "constant") that lexes as a keyword.

## Branches

- `typed-remarks` (off `develop`): opt-in reader benchmarks and this document.
- `typed-no-remarks` (on top of it): an experiment that removes remark support.
  It deletes every `[_remark]`, the `_REMARK`/`_remark` definitions and the
  template import, and makes the same textual edit to the committed generated
  grammars. That edit was checked against a scratch regeneration: only
  pre-existing DFN drift differs. **Not for merge.** It exists to measure
  things against.

## Remarks are load-bearing

The typed grammar was run over every package file of the 239 `KNOWN_PASSING`
corpus models (2,228 files):

| | failures |
|---|---|
| with remarks (`develop`) | 47 (exactly the `KNOWN_TYPED_GAPS` components) |
| without remarks | 404 |

357 files newly fail and none newly pass. The 2 `gwf-npf` gap files still
fail, because their remark has nowhere to go. The rejected remarks are:

- **~90%: labels trailing an array control line**, an MF2005-era convention
  that mf5to6-converted inputs carry over. Examples:
  - `CONSTANT 100.0 DELR` (146 `gwf-dis` files alone)
  - `INTERNAL FACTOR 1.0 IPRN -1 Initial head for layer 1`
  - `OPEN/CLOSE f.top FACTOR 1.0 IPRN 5 top layer 1`
- **Option lines**: `PRINT_INPUT (echo input to listing file)`,
  `SAVE_FLOWS flow15_flow.cbc`.
- **A few data rows**: `0 0 0 ... row 1`.

## Remarks cost (almost) nothing at runtime

Both variants were benchmarked on the same pinned 1,800 files (18.0 MB, 30
components). These are the files the no-remark grammar still parses. Figures
are the minimum of 3 rounds:

| stage | with remarks | without |
|---|---|---|
| typed parse | 11.15 s | 11.63 s |
| typed parse + transform | 15.24 s | 15.27 s |
| typed grammar build (30 components, once per process) | 1.71 s | 1.25 s |

The parse-stage differences are noise. `basic` parse, whose grammar is
unchanged, moved 3-5% between the same two runs. The one real cost is about
0.5 s of grammar construction per process. The transformer never sees
remarks, because Lark drops `_`-prefixed rules and terminals from the tree.

So the case for dropping remarks rests on grammar complexity and the 2-file
`gwf-npf` gap, not on speed.

Also: the claim that both lexer-priority tricks exist because of remarks
is only half right. `WORD_STR.-1`'s comment traces it to LALR state merging
between `integer+` rules and a trailing `word`. Only `_REMARK.-1` is
remark-specific.

## Options for a cheaper remark

1. **One rest-of-line terminal that can't start numeric**, roughly
   `/(?![-+.\d,])[^\n]+/`, instead of a run of word-like tokens.
   - The whole remark is one token, so a keyword inside it can't win. This
     should close the `gwf-npf` gap.
   - A remark can never start at a comma or number, which removes the
     remark-related reason for the `COMMA` carve-out.
   - Catch: after `CONSTANT 1.0`, a rest-of-line match beats the optional
     `IPRN 5` by maximal munch. It needs a lookahead excluding `iprn`,
     `factor` and `(binary)`, so some complexity moves rather than
     disappears.
2. **Allow remarks only where the corpus has them**: array control lines,
   option lines and data rows. Record/union/file fields and block headers may
   not need them. Verify each site by re-adding it and diffing the corpus
   failure set.
3. **Strip remarks before parsing**, with a per-line pass that knows each
   control line's arity. That's cheap for the ~90% on array control lines,
   but it's a second, non-grammar parser to keep in sync.
4. **Deprecate.** Keep today's grammar, count and warn when a remark is
   consumed (make `_remark` a named rule to see it in the transformer), and
   drop remarks in a later input-format version.

## Reproducing

```shell
# benchmarks (opt-in; ~4 min)
pixi run -e dev bench
pixi run -e dev bench --benchmark-compare          # vs. the last saved run

# A/B two grammar variants on identical input: write the manifest on the
# stricter variant first, then reuse it on the other
git switch typed-no-remarks
pixi run -e dev bench --bench-manifest /path/to/manifest.txt
git switch typed-remarks
pixi run -e dev bench --bench-manifest /path/to/manifest.txt --benchmark-compare
```

The corpus failure-set comparison used a scratch script that runs
`loads_typed` over `_collect_package_files` for every `KNOWN_PASSING` model,
with the `KNOWN_TYPED_GAPS` skip removed. That skip is the only difference
from `test_mf6_typed_grammar_corpus.py`.
