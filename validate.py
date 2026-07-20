#!/usr/bin/env python3
"""
Integrity checks for data/thug2-tricks.json.

Run this after editing the data by hand, and in CI on every pull request. It does
not need the game: it checks that the file is internally consistent, which is what
a well-meaning but wrong correction is most likely to break.

    python3 validate.py [path]
"""
import json
import sys

DIRECTIONS = {'up', 'down', 'left', 'right',
              'up-left', 'up-right', 'down-left', 'down-right'}
CATEGORIES = {'flip', 'grab', 'lip', 'manual', 'jump', 'revert', 'special', 'mode', 'other'}

failures = []


def check(name, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + ('' if ok else '   -> ' + str(detail)))
    if not ok:
        failures.append(name)


def walk(node, key_filter, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in key_filter:
                out.update(v if isinstance(v, list) else [v])
            else:
                walk(v, key_filter, out)
    elif isinstance(node, list):
        for v in node:
            walk(v, key_filter, out)


def main(path='data/thug2-tricks.json'):
    try:
        d = json.load(open(path))
    except Exception as exc:                       # noqa: BLE001
        print('FAIL  file does not parse as JSON   -> %s' % exc)
        return 1

    check('schemaVersion present', bool(d.get('schemaVersion')))
    check('provenance present', bool(d.get('provenance', {}).get('source')))
    check('knownGaps present', len(d.get('knownGaps', [])) > 0)
    # 'open' means a question we have raised but not answered. It is a real
    # state and must be expressible, otherwise the honest answer gets rounded
    # up to a confident one.
    valid_confidence = ('verified', 'inferred', 'open')
    check('every gap states its confidence',
          all(g.get('confidence') in valid_confidence for g in d['knownGaps']),
          [g.get('id') for g in d['knownGaps']
           if g.get('confidence') not in valid_confidence])

    # names
    named = (d['assignableTricks'] + d['tapVariants']
             + d['sharedBaseline']['bindings']
             + [s for c in d['characters'] for s in c['specials']])
    check('no empty trick names', all(t.get('name') for t in named))
    blank = [t['name'] for t in named if t['name'] != t['name'].strip()]
    check('no leading/trailing whitespace in names', not blank, blank[:5])
    markup = [t['name'] for t in named if '\\c' in t['name']]
    check('no leftover colour codes', not markup, markup[:5])

    # vocabularies
    dirs = set()
    walk(d, {'directions', 'direction'}, dirs)
    dirs.discard(None)
    check('all directions use the documented words', dirs <= DIRECTIONS, dirs - DIRECTIONS)

    buttons = set()
    walk(d, {'button', 'buttons'}, buttons)
    buttons.discard(None)
    check('all buttons appear in buttonMap',
          buttons <= set(d['buttonMap']), buttons - set(d['buttonMap']))

    cats = {t.get('category') for t in d['assignableTricks'] + d['tapVariants']}
    cats.discard(None)
    check('all categories are known', cats <= CATEGORIES, cats - CATEGORIES)

    # characters
    total = len(d['characters'])
    check('every character names a trickSet', all(c.get('trickSet') for c in d['characters']))
    check('every trickSet referenced exists',
          {c['trickSet'] for c in d['characters']} <= set(d['trickSets']),
          {c['trickSet'] for c in d['characters']} - set(d['trickSets']))
    check('every special has an input',
          all(s.get('input') for c in d['characters'] for s in c['specials']))

    # signature flag must agree with the data rather than be asserted
    counts = {}
    for c in d['characters']:
        for s in c['specials']:
            counts[s['name']] = counts.get(s['name'], 0) + 1
    bad_sig = [s['name'] for c in d['characters'] for s in c['specials']
               if s.get('signature') != (counts[s['name']] == 1)]
    check('signature flag matches how many characters have it', not bad_sig, bad_sig[:5])

    bad_also = [s['name'] for c in d['characters'] for s in c['specials']
                if len(s.get('alsoFactoryDefaultFor', [])) != counts[s['name']] - 1]
    check('alsoFactoryDefaultFor lists the right number', not bad_also, bad_also[:5])

    # share counts
    bad_share = [b['name'] for ts in d['trickSets'].values()
                 for b in ts['variableBindings']
                 if not (1 <= b.get('sharedByCharacters', 0) <= total)
                 or b.get('ofTotal') != total]
    check('share counts are within 1..%d' % total, not bad_share, bad_share[:5])

    # a baseline binding is by definition shared by everyone, so it must not
    # also turn up in a trickSet's variable list
    base_keys = {(b['name'], json.dumps(b.get('input'), sort_keys=True))
                 for b in d['sharedBaseline']['bindings']}
    clash = [b['name'] for ts in d['trickSets'].values() for b in ts['variableBindings']
             if (b['name'], json.dumps(b.get('input'), sort_keys=True)) in base_keys]
    check('no binding is both baseline and variable', not clash, clash[:5])

    # grinds and manuals
    fams = d['grinds']['families']
    check('exactly one neutral grind family',
          sum(1 for f in fams if f['direction'] is None) == 1)
    check('every grind family lists at least one trick', all(f['gives'] for f in fams),
          [f['direction'] for f in fams if not f['gives']])
    check('grind tap upgrades all resolve to names',
          all(t.get('upgradesTo') for t in d['grinds']['tapAgain']))
    check('manual entry routes exist', len(d['manuals']['entry']) >= 2)
    check('manual branches all named',
          all(r.get('name') for k in ('branchesFromAnyManual', 'branchesFromManual',
                                      'branchesFromNoseManual')
              for r in d['manuals'][k]))

    # duplicates
    ids = [t['internalId'] for t in d['assignableTricks']]
    check('no duplicate assignable internalIds', len(ids) == len(set(ids)),
          [i for i in ids if ids.count(i) > 1][:5])

    print()
    if failures:
        print('%d CHECK(S) FAILED' % len(failures))
        return 1
    print('ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'data/thug2-tricks.json'))
