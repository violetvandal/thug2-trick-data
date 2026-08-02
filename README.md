# THUG2 Trick Data

Machine-readable trick data for *Tony Hawk's Underground 2* (PC), extracted from the
game's own script files rather than transcribed from menus.

`data/thug2-tricks.json` covers:

| | |
|---|---|
| Assignable tricks | 186 |
| Tap variants | 53 |
| Grind names | 86 |
| Characters | 28 |
| Factory specials | 80 across those characters |

It also carries the parts no menu shows you: the grind direction table, the manual
branch tree, and how widely each default binding is shared across the roster.

## Why this exists

The in-game Edit Tricks menu only shows the tricks you currently have bound, so it is
not a list of what the game contains. Grinds and manuals are not in that menu at all,
which is why they are missing or wrong in most lists online.

## Provenance

Everything comes from `Data/pre/qb_scripts.prx` in a clean US PC install: 209 decompiled
`.qb` scripts, chiefly `alltricks`, `airtricks`, `groundtricks`, `liptricks`,
`manualtricks`, `grindscripts`, `grindlist`, `protricks` and `skater_profile`.

**No game assets are included here.** The dataset holds factual data only: trick names,
button inputs and base scores. To rebuild it you supply your own copy of the game.

Names and double-tap chains were checked against in-game menu captures, and the special
slots were round-tripped against the source: 86 assignments, zero undecoded slots, zero
unresolved names, zero type mismatches.

Trick names and base scores were also cross-checked against the tables in the BradyGames
official strategy guide (2004), which is what turned up the ten double-tap tricks listed
below. See `harness/xcheck_guide.py`; the guide itself is not included.

## Known gaps

These are recorded in the `knownGaps` field of the JSON, and they are the most useful
places to send a correction.

1. **Grind direction order is inferred.** `GrindTrickList` appears exactly once, as data.
   The code that picks a family from your direction lives in `THUG2.exe`, not in any
   script. The nine families are certain. The direction each maps to is inferred from
   their contents and matches series convention, but it was not read directly.
2. **Specials are factory defaults, not exclusivity.** The Edit Tricks menu builds its
   list from the global `ConfigurableTricks` array filtered by `TrickIsLocked`, which is
   save-file unlock state and not character identity. "Signature" in this data means only
   that one character ships with it.
3. **24 trick IDs are omitted.** They are listed in `alltricks.qb` but have no definition
   anywhere in the game files, so they carry no name, animation or score. They look like
   cut content. Their IDs are listed in `knownGaps` if you want to dig.
4. **Wall tricks and skitching are missing on purpose.** Wallrides, wallies, wallpush and
   skitching score points but have no scripted definition to read: the scripts hold only
   their animations, events and goal text, and the moves themselves live in `THUG2.exe`.
   The strategy guide prints scores for them; those are not copied in here, because
   everything in this file comes from the game data itself.
5. **Eric Sparrow is listed but cannot be played.** He has a complete profile, but he is
   the only roster entry with no `unlock_flag`, no `found_flag` and no
   `SKATER_UNLOCKED_*` global, so nothing in the shipped scripts can ever unlock him. He
   is here because the scripts define him. The other 27 each have a real unlock route,
   though only the Custom Skater has been hand-checked against the in-game menu.

## Rebuilding

```
python3 extract.py --game /path/to/THUG2 --ns /path/to/ns --toolkit /path/to/tools/prx
```

You need the NeverScript (THUG2 fork) decompiler and the `prx.py` / `lzss.py` helpers
from the Revert toolkit.

## Corrections

If a row disagrees with the game, please say what you did, which character and stance you
were on, and what actually happened. In-game behaviour wins over anything here.

## Licence

The data and scripts in this repository are MIT licensed. *Tony Hawk's Underground 2* is
the property of its respective rights holders. This project is unaffiliated.
