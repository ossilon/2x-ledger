# Style rules for public text

All public text in this repository follows ASD-STE100 (Simplified Technical English) with American spelling. The
rules make the text short, clear and the same from file to file. Numbers and facts never change for style.

## The rules

1. Write short sentences. A descriptive sentence has at most 25 words. An instruction has at most 20 words.
2. Write one topic in each sentence. Write one instruction in each sentence.
3. Use the active voice. Say who does what. Write `the engine computes the cost`, not `the cost is computed`.
4. Use the present tense where you can.
5. Do not use the -ing form of a verb as a noun or as a progressive tense. Write `the fund rebalances each day`,
   not `the fund is rebalancing each day`. The list below names the technical -ing words that the linter accepts.
6. Keep the articles. Write "the fund", "a window", "the rate".
7. Use simple words. Do not use slang, idiom, Latin abbreviations (`e.g.`, `i.e.`, `etc.`) or vague words
   (`very`, `quite`, `basically`, `stuff`).
8. Do not put more than three nouns in a row. Write "the cost of the fund each year", not "fund annual cost
   figure".
9. Use a list for a sequence of steps or items.
10. Keep paragraphs short: at most six sentences.
11. Use American spelling: behavior, license, center, modeling, analyze, gray.
12. Define each technical term once, in `docs/GLOSSARY.md`, and use the same term everywhere.

## Technical names

The linter accepts the technical names of the domain, -ing endings included. Each has one meaning in
`docs/GLOSSARY.md`:

```
underlying, rebalancing, financing, compounding, trading, listing, holding, timing, borrowing, lending,
pricing, rounding, funding, tracking, trailing, rolling, closing, opening, outstanding, remaining,
existing, ranking, drawdown, residual, variance ratio, swap, spread, leverage, hurdle, bootstrap, census
```

## The linter

`scripts/ste_check.py` reads every public Markdown file. It reports each sentence that breaks a rule it can test.
The rules it tests: sentence length, passive voice, -ing forms, banned words, British spelling and paragraph length.
It prints `N problem(s)` and returns exit code 1 when N is not zero. Run it with `scripts/scan_identifiers.py`
before each commit:

```
py -I scripts\ste_check.py
py -I scripts\scan_identifiers.py
```

The linter skips code blocks, inline code, link targets and the rows of `ledger.csv`. It cannot test the approved
word list of STE or the one-topic rule, so a reader checks those.
