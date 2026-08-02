#!/usr/bin/env python3
"""
Rebuild data/thug2-tricks.json from a THUG2 PC install.

    python3 extract.py --game /path/to/THUG2 --ns /path/to/ns --out data/thug2-tricks.json

Nothing from the game ships in this repo. This script reads YOUR copy, extracts
factual data (trick names, button inputs, base scores) and writes the JSON.

Needs:
  * a THUG2 PC install containing Data/pre/qb_scripts.prx
  * the NeverScript (THUG2 fork) decompiler binary, for -d
  * prx.py and lzss.py from the Revert toolkit, importable via --toolkit
"""
import argparse, collections, json, os, re, subprocess, sys, tempfile

DIRNAME = {'U': 'up', 'D': 'down', 'L': 'left', 'R': 'right', 'UL': 'up-left',
           'UR': 'up-right', 'DL': 'down-left', 'DR': 'down-right'}
BTN = {'square': 'flip', 'circle': 'grab', 'triangle': 'lip-grind'}
CAT = {'FlipTrick': 'flip', 'GrabTrick': 'grab', 'LipMacro2': 'lip', 'Manual': 'manual',
       'ManualLink': 'manual', 'Boneless': 'jump', 'Revert': 'revert'}
CLEAN = re.compile(r'\\+c\d')          # THUG2 inline colour codes, e.g. \c4 ... \c0
MODE = {'FireballF': 'Firefight', 'DoubleFireballF': 'Firefight',
        'TripleFireballF': 'Firefight', 'QuadFireballF': 'Firefight',
        'FireballB': 'Firefight', 'DoubleFireballB': 'Firefight',
        'TripleFireballB': 'Firefight', 'QuadFireballB': 'Firefight',
        'ScavengerF': 'Scavenger Hunt'}
SPECIAL_SLOT = {'extraslot1': 'Revert slot', 'extraslot2': 'Revert slot',
                'jumpslot': 'Jump / boneless slot'}


def unpack(prx_path, toolkit, workdir):
    """Extract + LZSS-decompress every .qb in qb_scripts.prx."""
    sys.path.insert(0, toolkit)
    import prx, lzss
    _ver, entries = prx.parse(open(prx_path, 'rb').read())
    n = 0
    for e in entries:
        name = e['name'].split(b'\0', 1)[0].decode('latin1')
        if not name.lower().endswith('.qb'):
            continue
        blob = (lzss.decompress(e['blob'], e['dsize']) if e['csize']
                else e['blob'][:e['dsize']])
        open(os.path.join(workdir, name.replace('\\', '__').replace('/', '__')),
             'wb').write(blob)
        n += 1
    return n


def decompile(ns_bin, workdir):
    for f in sorted(os.listdir(workdir)):
        if f.endswith('.qb'):
            subprocess.run([ns_bin, '-d', os.path.join(workdir, f),
                            '-o', os.path.join(workdir, f[:-3] + '.ns')],
                           capture_output=True)


def load(workdir):
    """basename-without-extension -> decompiled source, checksum table stripped."""
    out = {}
    for f in os.listdir(workdir):
        if f.endswith('.ns'):
            txt = open(os.path.join(workdir, f), errors='replace').read()
            out[f[:-3].replace('__', '/')] = txt.split('__register_checksums__')[0]
    return out


def parse_defs(corpus):
    """Every `Name = {...}` / `Name = [...]` block that carries a display name.

    Three traps live here, all found by checking output against in-game menus:
      * the key is `name=` in air/ground tricks but `Name=` in lip tricks
      * a block can set ExtraTricks TWICE; the game uses the LAST one
        (Trick_Benihana -> Sacktap, not Beni Fingerflip)
      * a double-tap trick names its script in one of TWO shapes. Most spell it
        out as `Trigger={...} Scr=FlipTrick`, but ten of them fuse trigger and
        script into a single token, `Trigger_Extra_Grab` / `Trigger_Extra_Flip`,
        and carry no `Scr=` at all. Reading only `Scr=` silently drops those ten
        real, player-facing tricks (BS Shifty, Tuck Knee, 360 Hardflip...), so
        the fused token is recorded here as `trigger` and treated as equivalent.
    """
    defs = {}
    for src, t in corpus.items():
        for m in re.finditer(r'(?m)^\s*(\w+)\s*=\s*(\[|\{)', t):
            tid, seg = m.group(1), t[m.start():m.start() + 900]
            name = re.search(r'\bname\s*=\s*%?"([^"]+)"', seg, re.I)
            if not name:
                continue
            nxt = re.search(r'\n\s*\w+\s*=\s*[\[\{]', seg[len(m.group(0)):])
            body = seg[:len(m.group(0)) + nxt.start()] if nxt else seg
            extras = re.findall(r'\bExtraTricks\s*=\s*(\w+)', body, re.I)
            score = re.search(r'\bscore\s*=\s*(\d+)', body, re.I)
            scr = re.search(r'\bScr\s*=\s*(\w+)', body, re.I)
            # Trigger_Extra_Grab_Tweak is a tweakable grab; the _Tweak suffix
            # affects how it is held, not what kind of trick it is.
            trig = re.search(r'\bTrigger_Extra_(Grab|Flip)\b', body, re.I)
            defs.setdefault(tid, {
                'id': tid, 'name': CLEAN.sub('', name.group(1)).strip(),
                'score': int(score.group(1)) if score else None,
                'extra': extras[-1] if extras else None,
                'scr': scr.group(1) if scr else None,
                'trigger': trig.group(1).capitalize() if trig else None,
                'special': bool(re.search(r'\bIsSpecial\b', body)), 'src': src})
    return defs


def slot_input(slot):
    """Decode a slot name into directions + button.

    Case-insensitive on purpose: the game data mixes capitalisation
    (SpAir_U_R_circle, Splip_D_U_Triangle) and a case-sensitive match
    silently drops those rows.

    Extra_* (press the button a second time) must stay distinct from Air_*
    or the two collide on the same key and overwrite each other.
    """
    s = slot.strip()
    pats = [
        (r'^Extra_(Square|Circle|Triangle)(?:Square|Circle|Triangle)?(UL|UR|DL|DR|U|D|L|R)$',
         lambda m: {'d': [m.group(2).upper()], 'b': BTN[m.group(1).lower()], 'x2': True}),
        (r'^Air_(Square|Circle)(UL|UR|DL|DR|U|D|L|R)$',
         lambda m: {'d': [m.group(2).upper()], 'b': BTN[m.group(1).lower()]}),
        (r'^Lip_Triangle(UL|UR|DL|DR|U|D|L|R)$',
         lambda m: {'d': [m.group(1).upper()], 'b': 'lip-grind'}),
        (r'^Air_([UDLR])_([UDLR])_(Square|Circle)$',
         lambda m: {'d': [m.group(1).upper(), m.group(2).upper()], 'b': BTN[m.group(3).lower()]}),
        (r'^Sp(?:Air|Grind|Man|Lip)_([UDLR])_([UDLR])_(Square|Circle|Triangle)$',
         lambda m: {'d': [m.group(1).upper(), m.group(2).upper()], 'b': BTN[m.group(3).lower()]}),
    ]
    for pat, fn in pats:
        m = re.match(pat, s, re.I)
        if m:
            return fn(m)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', required=True, help='THUG2 install root')
    ap.add_argument('--ns', required=True, help='NeverScript binary')
    ap.add_argument('--toolkit', default='tools/prx', help='dir holding prx.py + lzss.py')
    ap.add_argument('--out', default='data/thug2-tricks.json')
    ap.add_argument('--keep', help='keep decompiled scripts in this dir')
    a = ap.parse_args()

    prx_path = os.path.join(a.game, 'Data', 'pre', 'qb_scripts.prx')
    if not os.path.exists(prx_path):
        sys.exit('not found: %s\nPoint --game at a THUG2 PC install.' % prx_path)

    work = a.keep or tempfile.mkdtemp(prefix='thug2qb-')
    os.makedirs(work, exist_ok=True)
    print('unpacking %s' % prx_path)
    print('  %d .qb files' % unpack(prx_path, a.toolkit, work))
    print('decompiling with %s' % a.ns)
    decompile(a.ns, work)
    corpus = load(work)
    print('  %d scripts decompiled' % len(corpus))

    defs = parse_defs(corpus)
    print('  %d definitions carry a display name' % len(defs))
    # The remaining assembly (trick sets, characters, grinds, manuals) mirrors
    # build_dataset.py, kept separate so this file stays a readable reference
    # for how the raw scripts are read.
    from build_dataset import assemble
    data = assemble(corpus, defs, slot_input, DIRNAME, CAT, MODE, SPECIAL_SLOT, CLEAN)
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    json.dump(data, open(a.out, 'w'), indent=2)
    print('wrote %s (%.1f KB)' % (a.out, os.path.getsize(a.out) / 1024))
    if not a.keep:
        print('(decompiled scripts were temporary; pass --keep DIR to inspect them)')


if __name__ == '__main__':
    main()
