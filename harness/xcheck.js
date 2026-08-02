const {JSDOM}=require('jsdom'), fs=require('fs'), path=require('path');
// Paths resolve against this file rather than the shell's cwd, so it runs anywhere.
const page=path.join(__dirname,'standalone-page.html');
const dom=new JSDOM('<!doctype html><html><body>'+fs.readFileSync(page,'utf8')+'</body></html>',{runScripts:'dangerously'});
const d=dom.window.document, w=dom.window;
// The roster is read straight from the dataset, so the page is always compared
// against the current source of truth instead of a stale side-car copy.
const raw=JSON.parse(fs.readFileSync(
  path.join(__dirname,'..','data','thug2-tricks.json'),'utf8')).characters;
const sel=d.getElementById('sk-filter');
let fail=0, totalRendered=0;
function t(n,c,e){console.log((c?'PASS  ':'FAIL  ')+n+(c?'':'   -> '+e));if(!c)fail++;}

// walk every skater in the dropdown and compare row counts to the source
raw.forEach(s=>{
  sel.value=s.name; sel.dispatchEvent(new w.Event('change'));
  const cards=[...d.querySelectorAll('#specials .card')];
  const rows=cards.length?[...cards[0].querySelectorAll('tbody tr')]:[];
  totalRendered+=rows.length;
  if(rows.length!==s.specials.length)
    t('rows match source for '+s.name, false, `page=${rows.length} source=${s.specials.length}`);
  // every rendered row must have a glyph and a non-empty name
  rows.forEach(r=>{
    if(!r.querySelector('.btn')) t(s.name+' row has button glyph', false, r.textContent.trim());
    if(!r.querySelector('.tname').textContent.trim()) t(s.name+' row has a name', false, '(blank)');
  });
});
t('every skater rendered the right row count', fail===0, fail+' mismatches');
const srcTotal=raw.reduce((a,s)=>a+s.specials.length,0);
t('total rendered specials == source total ('+srcTotal+')', totalRendered===srcTotal,
  'rendered='+totalRendered);

// manual specials specifically reach the page
sel.value='*'; sel.dispatchEvent(new w.Event('change'));
const allTxt=d.getElementById('specials').textContent;
const manualSpecials=['One Wheel Nosemanual','Surfer','Yeah Right','Primo Spin','Rusty Slide Manual',
  'Primo','Flip 2 Switch','Boomerang','Slam Spinner','Hot Rod','Paulie Butt Manual',
  'Manual Entertainer','Running Manual'];
manualSpecials.forEach(n=>t('manual special on page: '+n, allTxt.indexOf(n)>-1));
console.log(fail?('\n'+fail+' FAILURES'):'\nCROSS-CHECK CLEAN');
process.exit(fail?1:0);
