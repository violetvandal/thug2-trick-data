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


_BTN_ORDER = {'flip': 0, 'grab': 1, 'lip-grind': 2}
_DIR_ORDER = ['D', 'DL', 'DR', 'L', 'R', 'U', 'UL', 'UR']


def _sort_key(row):
    """Order rows the way the in-game menus do: by button, then direction.
    Reads the INTERNAL input shape, so call this before public() renames keys."""
    i = row.get('input')
    if not i:
        return (4, 0, 9, 9)
    return (_BTN_ORDER.get(i['b'], 3),
            1 if i.get('x2') else 0,
            len(i['d']),
            _DIR_ORDER.index(i['d'][0]) if i['d'][0] in _DIR_ORDER else 9)


def _strip_stance(name):
    """Drop a leading FS/BS so grind families read as one trick, not two."""
    return re.sub(r'^(FS|BS)\s+', '', name) if name else name


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
        inp = slot_input(slot)
        label = special_slot.get(slot.lower())
        if not inp and not label:
            continue
        v = names.get(tid) or {}
        key = ((tuple(inp['d']), inp['b'], bool(inp.get('x2'))) if inp
               else ('slot', label, False))
        rows[key] = {
            'input': inp, 'slot': label,
            'name': names.of(tid) or tid.replace('Trick_', ''),
            'doubleTap': names.of(v.get('extra')) if v.get('extra') else None,
            'category': cat_of(tid), 'score': v.get('score'),
        }
    return rows


# ---------------------------------------------------------------- characters

def _parse_characters(profile):
    """master_skater_list, split on display_name so each block is one character."""
    start = profile.find('master_skater_list = [')
    seg = profile[start:]
    marks = [m.start() for m in re.finditer(r'display_name\s*=\s*"', seg)] + [len(seg)]
    out = []
    for i in range(len(marks) - 1):
        b = seg[marks[i]:marks[i + 1]]
        mapping = re.search(r'default_trick_mapping\s*=\s*(\w+)', b)
        out.append({
            'name': re.search(r'display_name\s*=\s*"([^"]*)"', b).group(1),
            'mapping': mapping.group(1) if mapping else None,
            'specials': [(s, t) for s, t in
                         re.findall(r'trickslot=(\w+)\s+trickname=(\w+)', b)
                         if s != 'Unassigned'],
        })
    return out


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
        out = {'directions': [dirname[d] for d in inp['d']], 'button': inp['b']}
        if inp.get('x2'):
            out['pressTwice'] = True
        return out

    sets = _parse_sets(corpus.get('scripts/game/skater/protricks', ''))
    loadouts = {m: _build_loadout(sets, names, m, slot_input, cat_of, special_slot)
                for m in MAP_ORDER if m in sets}
    characters = _parse_characters(corpus.get('scripts/game/skater/skater_profile', ''))
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
    chars_out = []
    for c in characters:
        sp = []
        for slot, tid in c['specials']:
            n = names.of(tid) or tid.replace('Trick_', '')
            v = names.get(tid) or {}
            sp.append({'name': n, 'input': fmt(slot_input(slot)), 'score': v.get('score'),
                       'signature': freq[n] == 1,
                       'alsoFactoryDefaultFor': [x for x in sp_owner[n] if x != c['name']]})
        chars_out.append({'name': c['name'], 'trickSet': c['mapping'], 'specials': sp})

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
            {'id': 'undefined-trick-ids', 'confidence': 'verified',
             'detail': '%d trick IDs are listed in alltricks.qb but have no definition '
                       'anywhere in the game files, so they carry no name, animation or '
                       'score. They appear to be cut content and are omitted.'
                       % len(undefined),
             'ids': undefined}]),
        ('buttonMap', {
            'flip': {'playstation': 'Square', 'xbox': 'X', 'gamecube': 'B'},
            'grab': {'playstation': 'Circle', 'xbox': 'B', 'gamecube': 'A'},
            'lip-grind': {'playstation': 'Triangle', 'xbox': 'Y', 'gamecube': 'Y'}}),
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
