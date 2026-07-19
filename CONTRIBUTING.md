# Corrections

The data here was read from the game's scripts, not typed out by hand, so most
errors will be in how something was interpreted rather than a typo. The most
likely candidates are listed as `knownGaps` in the JSON.

**In-game behaviour wins over anything in this repo.** If a row disagrees with
what the game does, the row is wrong.

## Reporting one

Open an issue and say:

1. Which trick, and where you saw it (character, section)
2. What the data claims
3. What the game actually does
4. Your character and stance, since several bindings vary by both

## The one that most needs checking

`knownGaps` records that the grind direction order is **inferred**. The nine
grind families are certain, because they are listed as data, but the code that
picks a family from the direction you hold lives in `THUG2.exe` and not in any
script. If you can confirm or correct any direction-to-grind mapping from
in-game testing, that is the single most valuable correction you can send.

## Changing the data

`data/thug2-tricks.json` is generated. If you can, describe the fix and let a
maintainer regenerate it. If you edit the file directly, run:

    python3 validate.py

CI runs the same checks on every pull request. They will not catch a wrong
trick name, but they will catch a change that breaks the file's internal
consistency, such as a `signature` flag that no longer matches how many
characters actually have that special.
