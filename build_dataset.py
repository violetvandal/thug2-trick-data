#!/usr/bin/env python3
"""
Assemble the public dataset from decompiled THUG2 scripts.

extract.py handles unpack -> decompile -> parse definitions, then calls assemble()
here. Split in two so extract.py stays a readable account of how the raw scripts
are read, and the fiddly cross-referencing lives on its own.

Every non-obvious rule below is commented with WHY, because most of them exist
because a first, reasonable-looking implementation produced wrong output that was
only caught by checking against the game.
"""
import collections
import re

MAP_LABELS = {
    'CustomTricks': 'Custom Skater', 'HawkTricks': 'Tony Hawk',
    'KostonTricks': 'Eric Koston', 'MargeraTricks': 'Bam Margera',
    'MullenTricks': 'Rodney Mullen', 'MuskaTricks': 'Chad Muska',
    'BurnquistTricks': 'Bob Burnquist', 'VallelyTricks': 'Mike Vallely',
    'PedTricks': 'Sheckler and guests',
}
MAP_ORDER = list(MAP_LABELS)
BTN_FROM_WORD = {'square': 'flip', 'circle': 'grab', 'triangle': 'lip-grind'}
GRIND_DIRS = [None, 'U', 'D', 'L', 'R', 'UL', 'UR', 'DL', 'DR']
TAP_DIR = {'UpRight': 'UR', 'DownRight': 'DR', 'DownLeft': 'DL', 'UpLeft': 'UL',
           'Up': 'U', 'Down': 'D', 'Left': 'L', 'Right': 'R'}


# ---------------------------------------------------------------- small helpers

def _bracket_block(text, start_idx):
    """Return the contents of the [...] beginning at start_idx, brackets balanced."""
    depth, out = 0, ''
    for ch in text[start_idx:]:
        if ch == '[':
            depth += 1
            if depth == 1:
                continue
        elif ch == ']':
            depth -= 1
            if depth == 0:
                break
        out += ch
    return out


def _named_block(text, key):
    m = re.search(r'(?m)^\s*' + re.escape(key) + r'\s*=\s*\n?\s*\[', text)
    return _bracket_block(text, m.end() - 1) if m else ''


def _rows_of(text, start_idx):
    """Split a list-of-lists into its top-level [...] rows."""
    rows, depth, cur = [], 0, ''
    for ch in text[start_idx:]:
        if ch == '[':
            depth += 1
            if depth == 1:
                cur = ''
                continue
        elif ch == ']':
            depth -= 1
            if depth == 0:
                rows.append(cur)
                continue
            if depth < 0:
                break
        if depth >= 1:
            cur += ch
    return rows


# ---------------------------------------------------------------- name lookup

class Names:
    """Resolve an internal trick id to its display name.

    Lookups are case-insensitive because the scripts are inconsistent
    (Trick_Sacktap vs Trick_SackTap, SpAir_U_R_circle vs ..._Circle).
    """

    def __init__(self, defs, corpus, clean):
        self.defs = defs
        self.clean = clean
        self.lower = {k.lower(): k for k in defs}
        # Grind tricks are not top-level definitions. They appear inside trigger
        # lists as `Scr=Trick_X Params={Name="FS 50-50"}`, so index those too.
        self.grind = {}
        self.alias = {}
        for src in ('scripts/game/skater/grindscripts', 'scripts/game/skater/grindlist'):
            text = corpus.get(src, '')
            # (a) trigger entries: Scr=Trick_X Params={Name="FS 50-50"}
            for m in re.finditer(r'Scr=(\w+)\s+Params=\{[^}]*?\bName\s*=\s*%?"([^"]+)"',
                                 text, re.I):
                self.grind.setdefault(m.group(1).lower(), m.group(2))
            # (b) script bodies: script Trick_X { Grind {Name="Double Blunt Slide" ...
            #     Several tap-upgrade grinds are named ONLY here.
            for m in re.finditer(
                    r'script\s+(\w+)\s*\{[^{}]*\{[^{}]*?\bName\s*=\s*%?"([^"]+)"',
                    text, re.I):
                self.grind.setdefault(m.group(1).lower(), m.group(2))
            # (c) aliases: script Trick_X { Goto Trick_Y ... }  (X has no name of its own)
            for m in re.finditer(r'script\s+(\w+)\s*\{\s*Goto\s+(\w+)', text, re.I):
                self.alias.setdefault(m.group(1).lower(), m.group(2))
        self.all_grind_names = sorted(set(
            re.findall(r'\bName\s*=\s*%?"([^"]+)"',
                       corpus.get('scripts/game/skater/grindscripts', ''))))
        self._norm = {re.sub(r'[^a-z0-9]', '', n.lower()): n for n in self.all_grind_names}

    def get(self, tid):
        tid = (tid or '').strip()
        return self.defs.get(tid) or self.defs.get(self.lower.get(tid.lower(), ''))

    def of(self, tid):
        v = self.get(tid)
        return self.clean.sub('', v['name']).strip() if v else None

    def grind_of(self, tid, _depth=0):
        """Grind ids carry _FS/_BS/_180/_FS_rot suffixes the name table omits."""
        tid = tid or ''
        for k in (tid,
                  re.sub(r'_(BS|FS)(_180)?$', '', tid),
                  re.sub(r'_FS_rot$', '', tid)):
            if k.lower() in self.grind:
                return self.grind[k.lower()]
            if self.of(k):
                return self.of(k)
        # follow `script X { Goto Y }` aliases; depth-capped against a cycle
        if _depth < 4 and tid.lower() in self.alias:
            found = self.grind_of(self.alias[tid.lower()], _depth + 1)
            if found:
                return found
        base = re.sub(r'[^a-z0-9]', '',
                      re.sub(r'^Trick_', '', re.sub(r'_(BS|FS)(_180)?$', '', tid)).lower())
        for cand in (base, 'fs' + base, 'bs' + base):
            if cand in self._norm:
                return self._norm[cand]
        # last resort: a name that contains the id, e.g. NosegrindPivot ->
        # "Nosegrind to Pivot", GrindOverturn -> "FS 5-0 Overturn"
        loose = [n for k, n in self._norm.items() if base and base in k]
        if loose:
            return sorted(loose, key=len)[0]
        return None


# The three slots whose names carry no direction. Their triggers live in
# groundtricks.qb rather than in the binding table, so they read as "no input"
# unless you go and look them up:
#   Jumptricks = [{Trigger={TapTwiceRelease, Up, X, 500} TrickSlot=JumpSlot}]
#   Reverts    = [{Trigger={Press, R2, 200} TrickSlot=ExtraSlot1} ...]
# Links the scripts do not express, confirmed by playing the game. Kept explicit
# and separate from anything parsed, so it is obvious which claims rest on
# testing rather than on the files, and so a future correction can overturn one
# without touching the parser.
#
# Bigfoot's board: chainsaw_params carries Motoskateboard_AirTricks (Hairy Foot
# Grab, Bigfoot Flip) but no profile field ties it to a character. Confirmed
# in-game 2026-07-19 that these are Bigfoot's.
PLAYTEST_CONFIRMED_VEHICLES = {
    'Chainsaw Skater': 'chainsaw_params',
}

SLOT_INPUTS = {
    'jumpslot': {'d': ['U', 'U'], 'b': 'jump'},
    'extraslot1': {'d': [], 'b': None, 'shoulder': 'R2'},
    'extraslot2': {'d': [], 'b': None, 'shoulder': 'L2'},
}

_BTN_ORDER = {'flip': 0, 'grab': 1, 'lip-grind': 2, 'jump': 3}
_DIR_ORDER = ['D', 'DL', 'DR', 'L', 'R', 'U', 'UL', 'UR']


def _sort_key(row):
    """Order rows the way the in-game menus do: by button, then direction.
    Reads the INTERNAL input shape, so call this before public() renames keys."""
    i = row.get('input')
    if not i:
        return (5, 0, 9, 9)
    dirs = i.get('d') or []
    # shoulder-only slots (the reverts) carry no direction and no face button
    return (_BTN_ORDER.get(i.get('b'), 4),
            1 if i.get('x2') else 0,
            len(dirs),
            _DIR_ORDER.index(dirs[0]) if dirs and dirs[0] in _DIR_ORDER else 9)


def _strip_stance(name):
    """Drop a leading FS/BS so grind families read as one trick, not two."""
    return re.sub(r'^(FS|BS)\s+', '', name) if name else name




def _parse_aerial_flips(airtricks):
    """Whole-body rotations. A different shape again: no Trigger, just a pair of
    directions (`button1=Down button2=Down`), which is why the sweep misses them.
    Roll resolves to BS/FS at runtime depending on which way you are facing."""
    body = _named_block(airtricks, 'AerialFlips')
    out = []
    for m in re.finditer(
            r'button1=(\w+)\s+button2=(\w+)[^}]*?name="([^"]+)"[^}]*?score=(\d+)', body, re.I):
        d1, d2, label, score = m.groups()
        key = (label, d1.lower())
        out.append({'name': label,
                    'directions': [d1.capitalize(), d2.capitalize()],
                    'score': int(score)})
    return out

# ---------------------------------------------------------------- general sweep

_TRIGGER_FORMS = [
    # (regex over the trigger body, builder)
    (r'^Press,\s*(\w+)', lambda g: {'buttons': [g[0]]}),
    (r'^PressAndRelease,\s*(\w+),\s*(\w+)', lambda g: {'d': [g[0]], 'buttons': [g[1]]}),
    (r'^TapTwiceRelease,\s*(\w+),\s*(\w+)', lambda g: {'d': [g[0], g[0]], 'buttons': [g[1]]}),
    (r'^InOrder,\s*(?:a=)?(\w+),\s*(?:b=)?(\w+)', lambda g: {'buttons': [g[0], g[1]]}),
    (r'^TripleInOrder(?:Sloppy)?,\s*(\w+),\s*(\w+),\s*(\w+)',
     lambda g: {'d': [g[0], g[1]], 'buttons': [g[2]]}),
    (r'^AirTrickLogic,\s*(\w+),\s*(\w+)', lambda g: {'buttons': [g[0]], 'd': [g[1]]}),
]
_DIR_WORD = {'up': 'U', 'down': 'D', 'left': 'L', 'right': 'R',
             'upleft': 'UL', 'upright': 'UR', 'downleft': 'DL', 'downright': 'DR'}
_SHOULDER = {'l1', 'l2', 'r1', 'r2'}


def _sweep_triggered_tricks(corpus, clean):
    """Every `{Trigger={...} ... Name="..."}` in the skater scripts.

    The targeted parsers above each read ONE named list, which means a trick
    defined in a list nobody thought to look up is silently absent. That is how
    Backflip, the manual spins and the kickflip-to-grab blends went missing. This
    sweep is deliberately shape-based rather than name-based so a list we have
    never heard of still shows up.
    """
    found = {}
    for src, text in corpus.items():
        if '/skater/' not in src and not src.endswith('groundtricks'):
            continue
        for m in re.finditer(
                r'\{Trigger=\{([^{}]*)\}(.*?)\bName\s*=\s*%?"([^"]{2,60})"',
                text, re.I | re.S):
            body, between, label = m.group(1), m.group(2), clean.sub('', m.group(3)).strip()
            if len(between) > 260:          # the Name belongs to a later entry
                continue
            entry = None
            for pattern, build in _TRIGGER_FORMS:
                hit = re.match(pattern, body.strip(), re.I)
                if hit:
                    entry = build([g for g in hit.groups()])
                    break
            if entry is None:
                continue
            out = {'name': label, 'source': src.rsplit('/', 1)[-1]}
            dirs, btns, shoulders = [], [], []
            for token in entry.get('d', []):
                key = token.lower().replace('_', '')
                if key in _DIR_WORD:
                    dirs.append(_DIR_WORD[key])
            for token in entry.get('buttons', []):
                low = token.lower()
                if low in BTN_FROM_WORD:
                    btns.append(BTN_FROM_WORD[low])
                elif low in _SHOULDER:
                    shoulders.append(token.upper())
                elif low == 'x':
                    btns.append('jump')
                elif low.replace('_', '') in _DIR_WORD:
                    dirs.append(_DIR_WORD[low.replace('_', '')])
            if dirs:
                out['d'] = dirs
            if btns:
                out['buttons'] = btns
            if shoulders:
                out['shoulder'] = shoulders[0]
            if not (dirs or btns or shoulders):
                continue
            found.setdefault(label, out)
    return found

# ---------------------------------------------------------------- trick sets

def _parse_sets(protricks):
    """Named binding tables, some of which include others by bare name."""
    sets = {}
    for m in re.finditer(r'(\w+)\s*=\s*\n?\s*\{((?:[^{}]|\{[^{}]*\})*?)\}', protricks):
        body = m.group(2)
        pairs = dict(re.findall(r'(\w+)\s*=\s*(Trick_\w+|#\w+|\w+)', body))
        includes = re.findall(r'(?m)^\s*(\w+)\s*$', body)
        if pairs or includes:
            sets[m.group(1)] = {'slots': pairs, 'includes': includes}
    return sets


def _resolve(sets, name, seen=None):
    """Flatten a set, applying its includes first so its own slots win."""
    seen = seen or set()
    if name in seen or name not in sets:
        return {}
    seen.add(name)
    out = {}
    for inc in sets[name]['includes']:
        if inc in sets:
            out.update(_resolve(sets, inc, seen))
    out.update(sets[name]['slots'])
    return out


def _build_loadout(sets, names, mapping, slot_input, cat_of, special_slot):
    """slot-key -> row. The key includes the press-twice flag, because
    Extra_SquareSquareL and Air_SquareL both mean "left + flip" and would
    otherwise overwrite each other, wrongly evicting Kickflip from the baseline."""
    rows = {}
    for slot, tid in _resolve(sets, mapping).items():
        if tid.startswith('#'):          # #xxxxxxxx = an empty slot
            continue
        inp = slot_input(slot) or SLOT_INPUTS.get(slot.lower())
        label = special_slot.get(slot.lower())
        if not inp and not label:
            continue
        v = names.get(tid) or {}
        # The key must capture EVERY part of the input that distinguishes one
        # binding from another. Leaving out press-twice once merged Kickflip with
        # Double Kickflip; leaving out the shoulder merged the two revert slots.
        key = ((tuple(inp.get('d') or ()), inp.get('b'), bool(inp.get('x2')),
                inp.get('shoulder')) if inp else ('slot', label, False, None))
        rows[key] = {
            'input': inp, 'slot': label,
            'name': names.of(tid) or tid.replace('Trick_', ''),
            'doubleTap': names.of(v.get('extra')) if v.get('extra') else None,
            'category': cat_of(tid), 'score': v.get('score'),
        }
    return rows


# ---------------------------------------------------------------- characters

def _parse_characters(profile):
    """master_skater_list, split on display_name so each block is one character.

    `vehicle_params` is the ONLY signal that a character rides something. Do not
    infer it from the ped profile's `board` field: that describes what the NPC
    model carries, so Bull Fighter and Ben Franklin look like they ride a bull
    and a segway when both are ordinary playable skaters. Bigfoot is the same,
    a normal skater whose board happens to be a chainsaw.

    `vehicle_params` matters: a character riding a vehicle uses the vehicle's own
    small trick set, not the skater specials listed in the same block. Steve-O's
    mechanical bull shows "Yee Haw!", never the Bite Board its profile lists.
    """
    start = profile.find('master_skater_list = [')
    seg = profile[start:]
    marks = [m.start() for m in re.finditer(r'display_name\s*=\s*"', seg)] + [len(seg)]
    out = []
    for i in range(len(marks) - 1):
        b = seg[marks[i]:marks[i + 1]]
        mapping = re.search(r'default_trick_mapping\s*=\s*(\w+)', b)
        vehicle = re.search(r'vehicle_params\s*=\s*(\w+)', b)
        appearance = re.search(r'default_appearance\s*=\s*(\w+)', b)
        out.append({
            'name': re.search(r'display_name\s*=\s*"([^"]*)"', b).group(1),
            'mapping': mapping.group(1) if mapping else None,
            'vehicle': vehicle.group(1) if vehicle else None,
            'appearance': appearance.group(1) if appearance else None,
            'specials': [(s, t) for s, t in
                         re.findall(r'trickslot=(\w+)\s+trickname=(\w+)', b)
                         if s != 'Unassigned'],
        })
    return out


def _merge_mounted_pairs(characters):
    """Collapse "X - Vehicle" / "X - Skater" into one character.

    The roster stores three characters twice, mounted and on foot. The pair
    differs ONLY in stats: the mounted profile pegs ollie and run to 1 and
    balance to 10-11, because those do not apply while riding. Tricks, specials
    and vehicle are identical, so a trick reference that keeps both prints
    everything twice and inflates every "shared by N characters" count.

    Merging here rather than at the end matters: the share counts and special
    frequencies are derived from this list, so a late merge leaves them
    describing a roster that no longer exists.
    """
    out, by_base = [], {}
    for c in characters:
        base, sep, variant = c['name'].partition(' - ')
        if not sep:
            out.append(c)
            continue
        prev = by_base.get(base)
        if prev and prev['specials'] == c['specials'] and prev['vehicle'] == c['vehicle']:
            prev['profiles'].append(variant)
            continue
        merged = dict(c, name=base, profiles=[variant])
        by_base[base] = merged
        out.append(merged)
    return out


def _parse_vehicles(vehicle_src):
    """Vehicles have their own four-trick vocabulary, defined per vehicle.

    Some also carry a real named trick list. The chainsaw board is the one that
    matters: it is Bigfoot's, and its Motoskateboard_AirTricks give him a Hairy
    Foot Grab and a Bigfoot Flip that exist nowhere else.
    """
    blocks = {}
    for m in re.finditer(r'(?m)^\s*(\w+)\s*=\s*\{', vehicle_src):
        seg = vehicle_src[m.start():m.start() + 2400]
        if 'trick_name' not in seg:
            continue

        def field(key):
            hit = re.search(key + r'\s*=\s*%?"([^"]+)"', seg)
            return hit.group(1) if hit else None

        blocks[m.group(1)] = ({
            'jump': field('jump_name'),
            'trick': field('trick_name'),
            'trick2': field('trick_name2'),
            'grind': field('grind_trick'),
        }, seg)

    # Named trick lists, attached to whichever params block drives the same anims.
    for m in re.finditer(r'(?m)^\s*(\w+)_AirTricks\s*=\s*\[', vehicle_src):
        body = _bracket_block(vehicle_src, m.end() - 1)
        named = [
            {'button': BTN_FROM_WORD.get(btn.lower(), btn.lower()),
             'name': label,
             'score': int(score) if score else None}
            for btn, label, score in re.findall(
                r'Trigger=\{Press,\s*(\w+),[^}]*\}[^}]*?name\s*=\s*%?"([^"]+)"'
                r'(?:[^}]*?Score\s*=\s*(\d+))?', body, re.I)
        ]
        if not named:
            continue
        prefix = m.group(1).lower()
        for vid, (data, seg) in blocks.items():
            if prefix in seg.lower():
                data['airTricks'] = named
    return {vid: data for vid, (data, _seg) in blocks.items()}



# ---------------------------------------------------------------- grinds

def _build_grinds(corpus, names):
    gl = corpus.get('scripts/game/skater/grindlist', '')
    gs = corpus.get('scripts/game/skater/grindscripts', '')

    m = re.search(r'GrindTrickList\s*=\s*\[', gl)
    families = []
    if m:
        # start AFTER the outer '[' so the first bracket seen is a row, not the
        # list itself (otherwise the whole table collapses into one "family")
        for i, row in enumerate(_rows_of(gl, m.end())):
            seen = []
            for tid in row.split():
                n = _strip_stance(names.grind_of(tid))
                if n and n not in seen:
                    seen.append(n)
            families.append({'direction': GRIND_DIRS[i] if i < len(GRIND_DIRS) else None,
                             'gives': seen})

    double = [{'d': [e.group(1)[0].upper(), e.group(2)[0].upper()],
               'name': _strip_stance(names.grind_of(e.group(3))) or e.group(3)}
              for e in re.finditer(
                  r'a=(\w+),\s*b=(\w+),\s*Triangle[^}]*\}[^}]*Prefix="(\w+)"', gl)]

    # Tap the grind button again mid-grind. FS and BS lists are separate but
    # give the same trick per direction, so merge them.
    taps = {}
    for stance in ('FS', 'BS'):
        block = _named_block(gs, 'GrindTaps_' + stance)
        for e in re.finditer(r'TripleInOrderSloppy,\s*(\w+),.*?Scr=(\w+)', block):
            d = TAP_DIR.get(e.group(1), e.group(1))
            n = _strip_stance(names.grind_of(e.group(2)))
            if n:
                taps.setdefault(d, n)
    return families, double, taps


# ---------------------------------------------------------------- manuals

def _build_manuals(corpus, names):
    mt = corpus.get('scripts/game/skater/manualtricks', '')

    entry = [{'d': [e.group(1)[0].upper(), e.group(2)[0].upper()],
              'name': names.of(e.group(3))}
             for e in re.finditer(
                 r'\{Trigger=\{InOrder,\s*(\w+),\s*(\w+),\s*\d+\}\s*Duration=\d+\s*(Trick_\w+)\}',
                 _named_block(mt, 'ManualTricks'))]

    # TRIGGER_MANUAL_BRANCHFLIP is a constant, resolve it rather than emit a token.
    bf = re.search(r'TRIGGER_MANUAL_BRANCHFLIP\s*=\s*\{InOrder,\s*a=(\w+),\s*b=(\w+)', mt)
    branchflip = ([BTN_FROM_WORD[bf.group(1).lower()], BTN_FROM_WORD[bf.group(2).lower()]]
                  if bf else ['flip', 'flip'])

    def branches(key):
        block, rows, seen = _named_block(mt, key), [], set()
        for e in re.finditer(
                r'\{Trigger=\{InOrder,\s*(?:a=)?(Square|Circle|Triangle),\s*'
                r'(?:b=)?(Square|Circle|Triangle),\s*\d+\}\s*(Trick_\s?\w+)\}', block):
            n = names.of(e.group(3).replace('Trick_ ', 'Trick_'))
            # Each branch is followed by a fallback back into Manual/Nose Manual;
            # that is the resting state, not a trick, so drop it.
            if not n or n in ('Manual', 'Nose Manual') or (e.group(1), e.group(2), n) in seen:
                continue
            seen.add((e.group(1), e.group(2), n))
            rows.append({'buttons': [BTN_FROM_WORD[e.group(1).lower()],
                                     BTN_FROM_WORD[e.group(2).lower()]], 'name': n})
        for e in re.finditer(
                r'\{Trigger=\{TripleInOrder,\s*(\w+),\s*(\w+),\s*'
                r'(Square|Circle|Triangle),\s*\d+\}\s*(Trick_\w+)\}', block):
            n = names.of(e.group(4))
            if n:
                rows.append({'d': [e.group(1)[0].upper(), e.group(2)[0].upper()],
                             'buttons': [BTN_FROM_WORD[e.group(3).lower()]], 'name': n})
        for e in re.finditer(r'\{Trigger=\{Press,\s*(R2|R1),\s*\d+\}\s*(Trick_\w+)', block):
            n = names.of(e.group(2))
            if n:
                rows.append({'shoulder': e.group(1), 'name': n})
        for e in re.finditer(r'Trigger=TRIGGER_MANUAL_BRANCHFLIP\s*(Trick_\w+)', block):
            n = names.of(e.group(1))
            if n:
                rows.append({'buttons': branchflip, 'name': n})
        return rows

    return entry, branches('FlatLandBranches'), branches('ManualBranches'), \
        branches('NoseManualBranches')


# ---------------------------------------------------------------- assembly

def assemble(corpus, defs, slot_input, dirname, cat, mode, special_slot, clean):
    names = Names(defs, corpus, clean)

    def cat_of(tid):
        v = names.get(tid) or {}
        return 'special' if v.get('special') else cat.get(v.get('scr'), 'other')

    def fmt(inp):
        if not inp:
            return None
        out = {'directions': [dirname[d] for d in inp.get('d', [])]}
        if inp.get('b'):
            out['button'] = inp['b']
        if inp.get('shoulder'):
            out['shoulder'] = inp['shoulder']
        if inp.get('x2'):
            out['pressTwice'] = True
        return out

    sets = _parse_sets(corpus.get('scripts/game/skater/protricks', ''))
    loadouts = {m: _build_loadout(sets, names, m, slot_input, cat_of, special_slot)
                for m in MAP_ORDER if m in sets}
    characters = _parse_characters(corpus.get('scripts/game/skater/skater_profile', ''))
    characters = _merge_mounted_pairs(characters)
    total = len(characters)

    by_mapping = collections.defaultdict(list)
    for c in characters:
        by_mapping[c['mapping']].append(c['name'])

    # How many characters share each exact (slot, trick) pair. A binding is
    # baseline only if every mapping agrees; everything else reports its share,
    # because "not universal" is very far from "unique to this skater".
    share, owners = collections.Counter(), collections.defaultdict(set)
    for m, rows in loadouts.items():
        for key, r in rows.items():
            share[(key, r['name'])] += len(by_mapping.get(m, []))
            owners[(key, r['name'])].update(by_mapping.get(m, []))

    all_keys = set().union(*[set(v) for v in loadouts.values()]) if loadouts else set()
    baseline_keys, varying = [], set()
    for k in all_keys:
        seen = {(loadouts[m][k]['name'] if k in loadouts[m] else None) for m in loadouts}
        if len(seen) == 1 and None not in seen:
            baseline_keys.append(k)
        else:
            varying.add(k)

    def sort_rows(rows):
        return sorted(rows, key=_sort_key)

    def public(r, extra=None):
        out = {'name': r['name'], 'input': fmt(r.get('input'))}
        if r.get('slot'):
            out['slot'] = r['slot']
        if r.get('doubleTap'):
            out['doubleTap'] = r['doubleTap']
        if r.get('score') is not None:
            out['score'] = r['score']
        if r.get('category'):
            out['category'] = r['category']
        if extra:
            out.update(extra)
        return out

    baseline = sort_rows([next(loadouts[m][k] for m in loadouts if k in loadouts[m])
                          for k in baseline_keys])
    trick_sets = {}
    for m, rows in loadouts.items():
        # Sort while the rows are still internal shape: sort_rows reads
        # input['b'], which public() renames to 'button'. Carry the key
        # alongside so the share count can be looked up after sorting.
        pairs = [(k, rows[k]) for k in varying if k in rows]
        pairs.sort(key=lambda kr: _sort_key(kr[1]))
        trick_sets[m] = {
            'label': MAP_LABELS.get(m, m),
            'variableBindings': [
                public(r, {'sharedByCharacters': share[(k, r['name'])], 'ofTotal': total})
                for k, r in pairs]}

    # specials: signature means only this character ships with it
    freq, sp_owner = collections.Counter(), collections.defaultdict(list)
    for c in characters:
        for _slot, tid in c['specials']:
            n = names.of(tid) or tid.replace('Trick_', '')
            freq[n] += 1
            sp_owner[n].append(c['name'])
    vehicles = _parse_vehicles(corpus.get('scripts/game/skater/skater_vehicle', ''))

    # Tricks triggered straight off the ground rather than through a slot, so they
    # appear in no binding table. No Comply is the notable one.
    ground = corpus.get('scripts/game/skater/groundtricks', '')
    ground_tricks = []
    seen_ground = set()
    for m in re.finditer(
            r'Trigger=\{PressAndRelease,\s*(\w+),\s*(\w+),\s*\d+\}[^}]*?'
            r'Params=\{Name\s*=\s*%?"([^"]+)"', ground, re.I):
        label = clean.sub('', m.group(3)).strip()
        if label in seen_ground:
            continue
        seen_ground.add(label)
        ground_tricks.append({
            'name': label,
            'input': {'directions': [dirname.get(m.group(1)[0].upper(), m.group(1))],
                      'button': 'jump'},
        })
    chars_out = []
    for c in characters:
        sp = []
        for slot, tid in c['specials']:
            n = names.of(tid) or tid.replace('Trick_', '')
            v = names.get(tid) or {}
            sp.append({'name': n, 'input': fmt(slot_input(slot)), 'score': v.get('score'),
                       'signature': freq[n] == 1,
                       'alsoFactoryDefaultFor': [x for x in sp_owner[n] if x != c['name']]})
        entry = {'name': c['name'], 'trickSet': c['mapping'], 'specials': sp}
        if len(c.get('profiles') or []) > 1:
            entry['profiles'] = c['profiles']
        # "Chainsaw Skater" is Bigfoot; the roster name hides who it is.
        if c.get('appearance'):
            entry['modelId'] = c['appearance']
        confirmed = PLAYTEST_CONFIRMED_VEHICLES.get(c['name'])
        if confirmed and not c.get('vehicle'):
            entry['board'] = {'id': confirmed,
                              'tricks': vehicles.get(confirmed, {}),
                              'source': 'confirmed in-game'}
        if c.get('vehicle'):
            # While mounted, the vehicle's own vocabulary replaces the skater
            # tricks above, which is why Steve-O's bull does "Yee Haw!" and never
            # the Bite Board his profile still lists.
            entry['vehicle'] = {'id': c['vehicle'],
                                'tricks': vehicles.get(c['vehicle'], {})}
        chars_out.append(entry)

    swept = _sweep_triggered_tricks(corpus, clean)

    # Two stragglers the sweep cannot see, both real:
    #   Chainsaw Grind lives in `script Trick_Motoskateboard_Grind`, so it is part
    #   of Bigfoot's board rather than a triggered trick.
    #   Truck Spin sits behind a `ProfileEquals is_named=mullen` guard.
    vehicle_src = corpus.get('scripts/game/skater/skater_vehicle', '')
    grind_hit = re.search(
        r'script\s+Trick_Motoskateboard_Grind\s*\{[^{}]*\{[^{}]*?name\s*=\s*%?"([^"]+)"',
        vehicle_src, re.I)
    if grind_hit and 'chainsaw_params' in vehicles:
        vehicles['chainsaw_params']['grind'] = grind_hit.group(1)
    mullen_only = re.search(
        r'ProfileEquals is_named=mullen.{0,400}?Name\s*=\s*%?"([^"]+)"',
        corpus.get('scripts/game/skater/manualtricks', ''), re.S | re.I)

    fams, gdouble, gtaps = _build_grinds(corpus, names)
    m_entry, m_flat, m_man, m_nose = _build_manuals(corpus, names)

    def mrow(r):
        out = {'name': r['name']}
        if r.get('d'):
            out['directions'] = [dirname[x] for x in r['d']]
        if r.get('buttons'):
            out['buttons'] = r['buttons']
        if r.get('shoulder'):
            out['shoulder'] = r['shoulder']
        return out

    configurable = sorted(set(re.findall(
        r'Trick_\w+', corpus.get('scripts/game/skater/alltricks', ''))))
    pool, undefined = [], []
    for tid in configurable:
        v = names.get(tid)
        if not v:
            undefined.append(tid)
            continue
        pool.append({'name': names.of(tid), 'category': cat_of(tid), 'score': v.get('score'),
                     'doubleTap': names.of(v['extra']) if v.get('extra') else None,
                     'internalId': tid})
    pool.sort(key=lambda x: x['name'].lower())

    in_pool = {p['internalId'].lower() for p in pool}
    variants = []
    for k, v in defs.items():
        if k.lower() in in_pool:
            continue
        if v.get('scr') in ('FlipTrick', 'GrabTrick', 'LipMacro2', 'Manual', 'ManualLink') \
                or v.get('special'):
            # Firefight / Scavenger Hunt tricks are scripted as FlipTricks but only
            # exist inside their mode, so they get their own category rather than
            # sitting in the flip list as mystery entries.
            category = ('mode' if k in mode
                        else 'special' if v.get('special')
                        else cat.get(v.get('scr'), 'other'))
            variants.append({
                'name': clean.sub('', v['name']).strip(),
                'category': category,
                'score': v.get('score'),
                'tapsAgainInto': names.of(v['extra']) if v.get('extra') else None,
                'gameMode': mode.get(k), 'internalId': k})
    variants.sort(key=lambda x: x['name'].lower())

    # Anything the targeted parsers already surfaced is not "other".
    covered = set()

    def seen(label):
        if label:
            covered.add(re.sub(r'\s+', ' ', label).strip().lower())

    for t in pool + variants:
        seen(t['name'])
        seen(t.get('doubleTap'))
        seen(t.get('tapsAgainInto'))
    for r in baseline:
        seen(r['name'])
        seen(r.get('doubleTap'))
    for rows in loadouts.values():
        for r in rows.values():
            seen(r['name'])
            seen(r.get('doubleTap'))
    for c in chars_out:
        for sp_entry in c['specials']:
            seen(sp_entry['name'])
    for group in (m_entry, m_flat, m_man, m_nose):
        for r in group:
            seen(r['name'])
    for name in names.all_grind_names:
        seen(name)
    for fam in fams:
        for name in fam['gives']:
            seen(name)
    for name in gtaps.values():
        seen(name)
    for g in gdouble:
        seen(g['name'])
    for g in ground_tricks:
        seen(g['name'])
    for v in vehicles.values():
        for key, val in v.items():
            if key == 'airTricks':
                for a in val:
                    seen(a['name'])
            else:
                seen(val)

    aerial = [
        {'name': a['name'],
         'directions': [dirname[_DIR_WORD[a['directions'][0].lower()]],
                        dirname[_DIR_WORD[a['directions'][1].lower()]]],
         'score': a['score']}
        for a in _parse_aerial_flips(corpus.get('scripts/game/skater/airtricks', ''))
    ]
    for a in aerial:
        seen(a['name'])

    other_tricks = []
    if mullen_only:
        swept.setdefault(mullen_only.group(1),
                         {'name': mullen_only.group(1), 'source': 'manualtricks',
                          'buttons': [], 'onlyFor': 'Rodney Mullen'})
    for label, info in sorted(swept.items()):
        if re.sub(r'\s+', ' ', label).strip().lower() in covered:
            continue
        row = {'name': label, 'foundIn': info['source']}
        if info.get('onlyFor'):
            row['onlyFor'] = info['onlyFor']
        if info.get('d'):
            row['directions'] = [dirname[x] for x in info['d']]
        if info.get('buttons'):
            row['buttons'] = info['buttons']
        if info.get('shoulder'):
            row['shoulder'] = info['shoulder']
        other_tricks.append(row)

    return collections.OrderedDict([
        ('schemaVersion', '1.0.0'),
        ('game', {'title': "Tony Hawk's Underground 2", 'platform': 'PC',
                  'region': 'US retail'}),
        ('provenance', {
            'source': 'Decompiled QB scripts from Data/pre/qb_scripts.prx of a clean '
                      'US PC install',
            'scriptsDecompiled': len(corpus),
            'toolchain': 'NeverScript (THUG2 fork) decompiler + prx/lzss unpacker',
            'note': 'No game assets are included. Only factual data: trick names, '
                    'button inputs and base scores.'}),
        ('knownGaps', [
            {'id': 'grind-direction-order', 'confidence': 'inferred',
             'detail': 'GrindTrickList appears once as data; the direction-to-family '
                       'selection happens in THUG2.exe, not in any script. The nine '
                       'families are certain, the direction each maps to is inferred '
                       'from their contents and matches series convention.'},
            {'id': 'specials-not-exclusive', 'confidence': 'verified',
             'detail': 'Per-character specials are FACTORY DEFAULTS, not exclusivity. '
                       'The Edit Tricks menu builds its list from the global '
                       'ConfigurableTricks array filtered by TrickIsLocked, which is '
                       'save-file unlock state and not character identity.'},
            {'id': 'roster-may-exceed-what-is-playable', 'confidence': 'open',
             'detail': 'master_skater_list is what the PC scripts DEFINE, which is not '
                       'proven to be what the PC build lets you PLAY. Eric Sparrow has a '
                       'full profile and four specials here, but did not appear as '
                       'playable after unlocking every skater in a real PC install '
                       '(2026-07-19). Some entries may be unused, cut, or carried over '
                       'from another edition of the game. Treat character and trick '
                       'availability as unverified until tested in-game.'},
            {'id': 'undefined-trick-ids', 'confidence': 'verified',
             'detail': '%d trick IDs are listed in alltricks.qb but have no definition '
                       'anywhere in the game files, so they carry no name, animation or '
                       'score. They appear to be cut content and are omitted.'
                       % len(undefined),
             'ids': undefined}]),
        ('buttonMap', {
            'flip': {'playstation': 'Square', 'xbox': 'X', 'gamecube': 'B'},
            'grab': {'playstation': 'Circle', 'xbox': 'B', 'gamecube': 'A'},
            'lip-grind': {'playstation': 'Triangle', 'xbox': 'Y', 'gamecube': 'Y'},
            'jump': {'playstation': 'X', 'xbox': 'A', 'gamecube': 'X'}}),
        ('aerialFlips', {
            'note': 'Whole-body rotations in the air, entered by holding a direction. '
                    'Roll shows as BS or FS depending on which way you are facing. The '
                    'script names the directions but not the button, so the button is '
                    'left unstated here rather than guessed.',
            'tricks': aerial}),
        ('otherTricks', {
            'note': 'Found by sweeping the scripts for trigger constructs rather than '
                    'by reading a known list. These are real, named and triggerable, '
                    'but they sit outside the loadout, grind and manual tables above.',
            'tricks': other_tricks}),
        ('groundTricks', {
            'note': 'Entered from the ground rather than from a slot binding.',
            'tricks': ground_tricks}),
        ('vehicles', {
            'note': 'A character riding a vehicle uses this short vocabulary instead '
                    'of their skater tricks. Only the characters listed under '
                    '"usedBy" ever mount one.',
            'sets': {vid: dict(
                v,
                usedBy=sorted({c['name'] for c in characters
                               if c.get('vehicle') == vid}),
                confirmedFor=sorted({name for name, v2 in
                                     PLAYTEST_CONFIRMED_VEHICLES.items() if v2 == vid}))
                for vid, v in vehicles.items()}}),
        ('sharedBaseline', {
            'description': 'Default slot bindings identical for all %d characters.' % total,
            'bindings': [public(r) for r in baseline]}),
        ('trickSets', trick_sets),
        ('characters', chars_out),
        ('grinds', {
            'note': 'Grinds are directional but are not listed in the Edit Tricks menu. '
                    'Frontside, backside and 180 variants are chosen from stance and '
                    'approach angle.',
            'families': [{'direction': dirname.get(f['direction']) if f['direction'] else None,
                          'gives': f['gives']} for f in fams],
            'tapAgain': [{'direction': dirname[d], 'upgradesTo': n}
                         for d, n in gtaps.items()],
            'doubleTapDirection': [{'directions': [dirname[x] for x in g['d']],
                                    'name': g['name']} for g in gdouble],
            'allNames': names.all_grind_names}),
        ('manuals', {
            'note': 'Manuals are not in the Edit Tricks menu either. Enter with two '
                    'directions, then press pairs of face buttons while balancing. '
                    'Branches chain indefinitely.',
            'entry': [mrow(r) for r in m_entry],
            'branchesFromAnyManual': [mrow(r) for r in m_flat],
            'branchesFromManual': [mrow(r) for r in m_man],
            'branchesFromNoseManual': [mrow(r) for r in m_nose]}),
        ('assignableTricks', pool),
        ('tapVariants', variants),
    ])
