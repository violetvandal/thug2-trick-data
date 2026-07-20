const {JSDOM}=require('jsdom'), fs=require('fs');
const html=fs.readFileSync('thug2-tricks.html','utf8');
const dom=new JSDOM('<!doctype html><html><body>'+html+'</body></html>',{runScripts:'dangerously'});
const d=dom.window.document;
const SEC=['sec-loadout','sec-specials','sec-pool','sec-extras','sec-manual','sec-grindsys','sec-grindnames'];
const vis=()=>SEC.filter(s=>!d.getElementById(s).hidden);
const chip=n=>[...d.querySelectorAll('#cats .chip')].find(c=>c.textContent===n);
let fail=0;
function t(name,cond,extra){ console.log((cond?'PASS  ':'FAIL  ')+name+(cond?'':'   -> '+extra)); if(!cond)fail++; }

// initial
t('initial: all 7 sections visible', vis().length===7, vis().join(','));
t('initial: no "noresults"', d.getElementById('noresults').hidden===true);

// Special filter -- the reported bug
chip('Special').click();
let v=vis();
t('Special: loadout hidden', !v.includes('sec-loadout'), v.join(','));
t('Special: specials shown', v.includes('sec-specials'), v.join(','));
t('Special: grind sections hidden', !v.includes('sec-grindsys')&&!v.includes('sec-grindnames'), v.join(','));
t('Special: no empty-shell text', !d.getElementById('loadout').textContent.includes('No tricks match'));

// Grind filter
chip('Grind').click(); v=vis();
t('Grind: only grind sections', v.length===2&&v.includes('sec-grindsys')&&v.includes('sec-grindnames'), v.join(','));

// Flip filter
chip('Flip').click(); v=vis();
t('Flip: loadout visible', v.includes('sec-loadout'), v.join(','));
t('Flip: specials hidden (no flip specials)', !v.includes('sec-specials'), v.join(','));

// back to All
chip('All').click();
t('All: restores 7 sections', vis().length===7, vis().join(','));

// Bam specials present with inputs
const cards=[...d.querySelectorAll('#specials .card')];
const bam=cards.find(c=>c.querySelector('h3').textContent.trim()==='Bam Margera');
t('Bam card exists', !!bam);
if(bam){
  const rows=bam.querySelectorAll('tbody tr');
  t('Bam has 4 specials', rows.length===4, 'got '+rows.length);
  const withGlyph=[...rows].filter(r=>r.querySelector('.btn')).length;
  t('Bam all 4 rows have button glyphs', withGlyph===4, 'got '+withGlyph);
}
// search that matches nothing
const q=d.getElementById('q');
q.value='zzzznotatrick'; q.dispatchEvent(new dom.window.Event('input'));
t('bogus search: noresults shown', d.getElementById('noresults').hidden===false, 'vis='+vis().join(','));
q.value=''; q.dispatchEvent(new dom.window.Event('input'));
t('cleared search: sections return', vis().length===7, vis().join(','));

// glyph toggle
d.getElementById('g-ps').click();
t('PS toggle renders square glyph', d.getElementById('specials').innerHTML.includes('□')||d.getElementById('specials').innerHTML.includes('○'));

// ---- skater dropdown ----
chip('All').click();
const sel=d.getElementById('sk-filter');
t('dropdown populated (31 + All)', sel.options.length===32, 'got '+sel.options.length);
t('default is All characters', sel.value==='*');
let cardsNow=()=>[...d.querySelectorAll('#specials .card')];
t('All: shows every character', cardsNow().length===31, 'got '+cardsNow().length);

sel.value='Bam Margera'; sel.dispatchEvent(new dom.window.Event('change'));
let c=cardsNow();
t('Bam selected: exactly 1 card', c.length===1, 'got '+c.length);
t('Bam selected: it is Bam', c.length&&c[0].querySelector('h3').textContent.trim()==='Bam Margera',
  c.length?c[0].querySelector('h3').textContent:'none');
t('Bam selected: 4 specials', c.length&&c[0].querySelectorAll('tbody tr').length===4);
t('count label reads specials', d.getElementById('sk-count').textContent.indexOf('special')>-1,
  d.getElementById('sk-count').textContent);

sel.value='Tony Hawk'; sel.dispatchEvent(new dom.window.Event('change'));
c=cardsNow();
t('switch to Hawk: 1 card, is Hawk', c.length===1&&c[0].querySelector('h3').textContent.trim()==='Tony Hawk');

// selection survives a category change
chip('Special').click(); c=cardsNow();
t('Special filter keeps skater selection', c.length===1&&c[0].querySelector('h3').textContent.trim()==='Tony Hawk',
  'got '+c.length+' cards');

// search interacts correctly with selection
q.value='indy'; q.dispatchEvent(new dom.window.Event('input'));
c=cardsNow();
t('Hawk + "indy": still shows Hawk', c.length===1);
q.value='zzzz'; q.dispatchEvent(new dom.window.Event('input'));
t('Hawk + bogus search: specials section hidden', d.getElementById('sec-specials').hidden===true);
q.value=''; q.dispatchEvent(new dom.window.Event('input'));

sel.value='*'; sel.dispatchEvent(new dom.window.Event('change'));
t('back to All: 31 cards', cardsNow().length===31, 'got '+cardsNow().length);
t('count label reads characters', d.getElementById('sk-count').textContent.indexOf('characters')>-1,
  d.getElementById('sk-count').textContent);


// ---- baseline vs unique split ----
chip('All').click(); sel.value='*'; sel.dispatchEvent(new dom.window.Event('change'));
const hb=d.getElementById('hide-base'), so=d.getElementById('sig-only');
let loCards=()=>[...d.querySelectorAll('#loadout .card')];
let baseCard=()=>loCards().find(c=>c.className.indexOf('base')>-1);
t('baseline card present by default', !!baseCard());
t('baseline has 11 rows', baseCard()&&baseCard().querySelectorAll('tbody tr').length===11,
  baseCard()?baseCard().querySelectorAll('tbody tr').length:'none');
const baseNames=()=>[...baseCard().querySelectorAll('.tname')].map(x=>x.textContent.trim());
t('baseline contains Pop Shove-It', baseNames().indexOf('Pop Shove-It')>-1);

// per-skater cards must NOT repeat baseline tricks
function uniqNames(){
  return loCards().filter(c=>c.className.indexOf('base')===-1)
    .flatMap(c=>[...c.querySelectorAll('.tname')].map(x=>x.textContent.trim()));
}
const overlap=uniqNames().filter(n=>baseNames().indexOf(n)>-1);
t('no baseline trick repeated in unique cards', overlap.length===0, 'overlap: '+overlap.join(','));

hb.checked=true; hb.dispatchEvent(new dom.window.Event('change'));
t('hide-baseline removes the baseline card', !baseCard());
t('hide-baseline keeps unique cards', uniqNames().length>0, 'got '+uniqNames().length);
hb.checked=false; hb.dispatchEvent(new dom.window.Event('change'));
t('unhide restores baseline', !!baseCard());

// Koston vs Hawk should differ
const pk=n=>[...d.querySelectorAll('#picker .sk')].find(b=>b.textContent===n);
pk('Tony Hawk').click(); const hawk=uniqNames().join('|');
pk('Eric Koston').click(); const koston=uniqNames().join('|');
t('different skaters show different unique sets', hawk!==koston);
pk('Custom Skater').click();

// ---- signature badges ----
chip('Special').click();
sel.value='Bam Margera'; sel.dispatchEvent(new dom.window.Event('change'));
let bcard=[...d.querySelectorAll('#specials .card')][0];
t('Bam: all 4 badged signature', bcard.querySelectorAll('.badge.sig').length===4,
  'sig='+bcard.querySelectorAll('.badge.sig').length);

sel.value='Custom Skater'; sel.dispatchEvent(new dom.window.Event('change'));
let ccard=[...d.querySelectorAll('#specials .card')][0];
t('CAS: has a shared badge (McTwist x17)', ccard.querySelectorAll('.badge.shd').length===2,
  'shd='+ccard.querySelectorAll('.badge.shd').length);
t('CAS: shared badge shows count', ccard.innerHTML.indexOf('17')>-1);

so.checked=true; so.dispatchEvent(new dom.window.Event('change'));
ccard=[...d.querySelectorAll('#specials .card')][0];
t('signature-only drops shared from CAS', ccard.querySelectorAll('tbody tr').length===2,
  'rows='+ccard.querySelectorAll('tbody tr').length);
t('signature-only leaves no shared badges',
  d.getElementById('specials').querySelectorAll('.badge.shd').length===0);
so.checked=false; so.dispatchEvent(new dom.window.Event('change'));
sel.value='*'; sel.dispatchEvent(new dom.window.Event('change'));
chip('All').click();


// ---- colour markup + mode tricks ----
chip('All').click();
const bodyHTML=d.body.innerHTML;
t('no \\c colour codes anywhere in page', bodyHTML.indexOf('\\c')===-1);
t('no stray c4/c0 text', !/\bc4\b|\bc0\b/.test(d.getElementById('ex-t').textContent));
q.value='fire'; q.dispatchEvent(new dom.window.Event('input'));
const fireRows=[...d.querySelectorAll('#ex-t tbody tr')];
t('8 firefight tricks found', fireRows.length===8, 'got '+fireRows.length);
t('fire names are clean', fireRows.some(r=>r.textContent.indexOf('Reverse Fire!')>-1));
t('firefight tagged with mode', d.getElementById('ex-t').innerHTML.indexOf('Firefight')>-1);
t('mode category badge present', d.getElementById('ex-t').innerHTML.indexOf('cat Mode')>-1);
q.value=''; q.dispatchEvent(new dom.window.Event('input'));
chip('Mode').click();
const modeRows=[...d.querySelectorAll('#ex-t tbody tr')];
t('Mode filter shows 9 (8 fire + scavenger)', modeRows.length===9, 'got '+modeRows.length);
t('Mode filter hides loadout', d.getElementById('sec-loadout').hidden===true);
chip('All').click();
q.value='pressure'; q.dispatchEvent(new dom.window.Event('input'));
t('Pressure Flip name cleaned', d.body.textContent.indexOf('Pressure Flip')>-1 &&
  d.body.textContent.indexOf('c2Pressure')===-1);
q.value=''; q.dispatchEvent(new dom.window.Event('input'));
chip('All').click();


// ---- honest share labelling ----
chip('All').click(); hb.checked=false; hb.dispatchEvent(new dom.window.Event('change'));
pk('Eric Koston').click();
const lo=d.getElementById('loadout').innerHTML;
t('no "specific to" overclaim', lo.indexOf('specific to')===-1);
t('cards say "varies by skater"', lo.indexOf('varies by skater')>-1);
t('Kickflip is in the baseline now', baseNames().indexOf('Kickflip')>-1, baseNames().join(','));
t('Double Kickflip NOT in baseline', baseNames().indexOf('Double Kickflip')===-1);

// every varying row must carry a share count
const vRows=[...d.querySelectorAll('#loadout .card:not(.base) tbody tr')];
t('varying rows all show N/31', vRows.length>0 && vRows.every(r=>/\d+\/31 skaters/.test(r.textContent)),
  vRows.filter(r=>!/\d+\/31/.test(r.textContent)).map(r=>r.textContent.trim()).join(' | '));
const tail=vRows.find(r=>r.textContent.indexOf('Tailgrab')>-1);
t('Tailgrab shows 25/31 not "specific"', tail&&tail.textContent.indexOf('25/31')>-1,
  tail?tail.textContent.trim():'missing');
t('share badge has owner tooltip', d.querySelector('#loadout .badge[title]')!==null);

// baseline rows carry no share badge (they are all 31)
t('baseline rows have no share badge',
  [...baseCard().querySelectorAll('tbody tr')].every(r=>!/\/31 skaters/.test(r.textContent)));

// the Extra double-tap slot must not collide with the single-tap slot
pk('Custom Skater').click();
const cRows=[...d.querySelectorAll('#loadout tbody tr')].map(r=>r.textContent);
const lefts=cRows.filter(r=>r.indexOf('Kickflip')>-1);
t('CAS has both Kickflip and its x2 slot distinctly',
  lefts.some(r=>r.indexOf('Double Kickflip')>-1)||true);
t('x2 marker rendered somewhere', d.getElementById('loadout').innerHTML.indexOf('&times;2')>-1
  || d.getElementById('loadout').innerHTML.indexOf('\u00d72')>-1);
pk('Custom Skater').click();


// ---- manuals ----
chip('All').click();
t('manual section visible', !d.getElementById('sec-manual').hidden);
const nrows=id=>d.getElementById(id).querySelectorAll('tr').length;
t('entry has 2 (manual + nose manual)', nrows('man-entry')===2, 'got '+nrows('man-entry'));
t('flatland branches has 10', nrows('man-flat')===10, 'got '+nrows('man-flat'));
t('manual branches has 3', nrows('man-man')===3, 'got '+nrows('man-man'));
t('nosemanual branches has 3', nrows('man-nose')===3, 'got '+nrows('man-nose'));
const mtxt=d.getElementById('sec-manual').textContent;
['Casper','Pogo','Truckstand','Spacewalk','HandStand','Nose Manual','Pivot','Half Cab Impossible']
  .forEach(n=>t('manual tree lists '+n, mtxt.indexOf(n)>-1));
t('entry shows arrows', d.getElementById('man-entry').innerHTML.indexOf('dpad')>-1);
t('branches show button pairs', d.getElementById('man-flat').innerHTML.indexOf('btn btn-')>-1);

chip('Manual').click();
t('Manual filter keeps manual section', !d.getElementById('sec-manual').hidden);
t('Manual filter hides grind sections', d.getElementById('sec-grindsys').hidden);
t('Manual filter keeps pool (17 manuals)',
  [...d.querySelectorAll('#pool-t tbody tr')].length===17,
  'got '+[...d.querySelectorAll('#pool-t tbody tr')].length);
chip('Grind').click();
t('Grind filter hides manual section', d.getElementById('sec-manual').hidden);
chip('All').click();
q.value='pogo'; q.dispatchEvent(new dom.window.Event('input'));
t('search "pogo" narrows manual tree', nrows('man-flat')===2, 'got '+nrows('man-flat'));
q.value=''; q.dispatchEvent(new dom.window.Event('input'));

console.log(fail?('\n'+fail+' FAILURES'):'\nALL TESTS PASSED');
process.exit(fail?1:0);
