"""The public site's HTML: one page, three tabs, no network but the fonts.

Split from site_build.py because the two answer different questions.
site_build decides WHAT is true -- which seasons exist, what they scored,
which forecast is the current one. This module decides how that is shown,
and holds the whole of the page's markup, CSS and behavior so the design is
reviewable in one file.

Constraints the page is built to, each of them tested:

  * OFFLINE FROM DISK. A reviewer opens site/index.html with a double click
    before deciding to commit it, so every asset is either inline or a
    sibling file. The one exception is the Google Fonts stylesheet, which
    degrades to the system stack when it cannot load.
  * PLOTLY IS A SIBLING, NOT AN INLINE BLOB. 4.9 MB inlined into the page
    would dominate every diff of a file whose diffs are the review. It
    ships as site/plotly.min.js, cached by the browser across visits and
    changed only when the library is upgraded.
  * NO UNRESOLVED PLACEHOLDERS. Anything the state cannot fund is omitted
    with a stated reason -- never rendered as an empty cell, a dash, or a
    number the build invented.
  * THEME-AWARE AND ACCESSIBLE. Light and dark from tokens, a high-contrast
    mode, and a colour-vision-safe categorical scale for the map, all
    stamped on the root element and persisted, mirroring the console's own
    accessibility controls.
"""
from __future__ import annotations

import html as _html
import json

CSS = """
:root{
  --bg:#F4F2FA; --card:#FFFFFF; --ink:#10122E; --mut:#5A5E7A;
  --accent:#0173A9; --gold:#8A6400; --line:#E3E1F0;
  --ok:#1E7A46; --bad:#B3263E; --hero1:#000F7E; --hero2:#0C0D17;
  --cat-large-decrease:#2e7d4f; --cat-decrease:#7fc97f; --cat-stable:#b9b09b;
  --cat-increase:#e8a33d; --cat-large-increase:#c0392b; --map-nodata:#d9d6e4;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0C0D17; --card:#14162B; --ink:#ECEAF6; --mut:#9DA1C0;
    --accent:#34C0F0; --gold:#FFC72C; --line:#262A45;
    --ok:#4CC38A; --bad:#FB4653; --hero2:#05060f; --map-nodata:#1d2035;
  }
}
:root[data-theme="dark"]{
  --bg:#0C0D17; --card:#14162B; --ink:#ECEAF6; --mut:#9DA1C0;
  --accent:#34C0F0; --gold:#FFC72C; --line:#262A45;
  --ok:#4CC38A; --bad:#FB4653; --hero2:#05060f; --map-nodata:#1d2035;
}
[data-vision="cvd"]{--cat-large-decrease:#2C7BB6;--cat-decrease:#ABD9E9;
 --cat-stable:#B9B09B;--cat-increase:#FDAE61;--cat-large-increase:#D7191C}
[data-contrast="high"]{--ink:#000014;--mut:#3D4060;--line:#8B87A5}
:root[data-theme="dark"][data-contrast="high"]{--ink:#FFFFFF;--mut:#C9CDF0;
 --line:#6B74B8}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:"DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
 line-height:1.55}
.mono,.n,td.n{font-family:"DM Mono",ui-monospace,SFMono-Regular,monospace}
a{color:var(--accent)}
header.site{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;
 padding:1rem clamp(1rem,4vw,3rem)}
.brandrow{display:flex;align-items:center;gap:.6rem}
.wordmark{font-weight:700;font-size:1.3rem}
.wordmark em{color:var(--accent);font-style:normal}
nav.tabs{display:flex;gap:.3rem;margin-left:1.4rem;flex-wrap:wrap}
nav.tabs button{font:inherit;font-size:.92rem;font-weight:500;background:none;
 border:none;color:var(--mut);padding:.45rem .8rem;border-radius:8px;
 cursor:pointer}
nav.tabs button[aria-pressed="true"]{color:var(--accent);background:var(--card);
 border:1px solid var(--line);font-weight:700}
nav.tabs button:focus-visible,.a11y button:focus-visible,
.mtoggle button:focus-visible,.fpick button:focus-visible,
.fpick select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.a11y{display:flex;gap:.3rem;margin-left:auto;flex-wrap:wrap}
.a11y button{font:inherit;font-size:.78rem;background:none;
 border:1px solid var(--line);color:var(--mut);border-radius:999px;
 padding:.22rem .7rem;cursor:pointer}
.a11y button[aria-pressed="true"]{color:var(--accent);border-color:var(--accent);
 font-weight:700}
main{max-width:min(94vw,88rem);margin:0 auto;
 padding:0 clamp(1rem,4vw,3rem) 4rem}
.page{display:none}.page.on{display:block}
section{margin-top:clamp(2.2rem,5vw,3.6rem)}
h2{font-size:clamp(1.3rem,1.1rem+.8vw,1.8rem);margin:0 0 .3rem}
h3{font-size:1.15rem;margin:.25rem 0 .45rem}
.kick{color:var(--accent);font-size:.95rem;letter-spacing:.09em;
 text-transform:uppercase;font-weight:700;margin-bottom:.35rem}
.sub{color:var(--mut);margin:.2rem 0 1.2rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
 padding:clamp(1rem,3vw,1.8rem)}
.banner{background:linear-gradient(120deg,var(--hero1),#0173A9);color:#F1EFF7;
 border-radius:14px;padding:1rem 1.4rem;margin-top:1rem;font-size:1.02rem}
.banner b{color:#34C0F0}
.standing{background:var(--card);color:var(--ink);border:1px solid var(--line)}
.standing .k{color:var(--accent);font-weight:700;letter-spacing:.08em;
 font-size:.74rem;text-transform:uppercase}
.maphero{background:var(--card);border:1px solid var(--line);
 border-radius:16px;padding:clamp(.8rem,2.5vw,1.6rem);margin-top:1rem}
.maptop{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;
 margin-bottom:.5rem}
.datebadge{font-family:"DM Mono",monospace;font-size:.85rem;color:var(--ink);
 background:var(--bg);border:1px solid var(--line);border-radius:999px;
 padding:.25rem .8rem}
.datebadge b{color:var(--accent)}
.mtoggle{display:flex;gap:.3rem;margin-left:auto;flex-wrap:wrap}
.mtoggle button{font:inherit;font-size:.82rem;background:none;
 border:1px solid var(--line);color:var(--mut);border-radius:999px;
 padding:.25rem .8rem;cursor:pointer}
.mtoggle button[aria-pressed="true"]{color:var(--accent);
 border-color:var(--accent);font-weight:700}
.legend{display:flex;flex-wrap:wrap;gap:.9rem;margin-top:.8rem;
 font-size:.82rem;color:var(--mut);align-items:center}
.sw{display:inline-block;width:.85em;height:.85em;border-radius:3px;
 margin-right:.35em;vertical-align:-.08em}
.asof{font-family:"DM Mono",monospace;font-size:.8rem;color:var(--mut)}
.prov{font-family:"DM Mono",monospace;font-size:.78rem;color:var(--mut);
 margin:.4rem 0 .6rem}
.fpick{display:flex;align-items:center;gap:.5rem;margin-bottom:.7rem;
 flex-wrap:wrap}
.fpick button{font:inherit;background:var(--card);border:1px solid var(--line);
 color:var(--ink);border-radius:8px;padding:.3rem .7rem;cursor:pointer}
.fpick select{font:inherit;background:var(--card);color:var(--ink);
 border:1px solid var(--line);border-radius:8px;padding:.35rem .6rem}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th{text-align:left;font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;
 color:var(--mut)}
th,td{padding:.55rem .8rem;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:none}
td.n,th.n{text-align:right}
td.n{font-family:"DM Mono",monospace}
.total td{font-weight:700}
.okc{color:var(--ok);font-weight:700}.badc{color:var(--bad);font-weight:700}
.na{color:var(--mut);font-style:italic}
.pct{display:flex;align-items:center;gap:.7rem;margin:.45rem 0}
.pct .bar{flex:1;height:.55rem;border-radius:999px;background:var(--line);
 overflow:hidden}
.pct .fill{height:100%;background:var(--accent)}
.pct .lab{width:5.5rem;font-size:.85rem;color:var(--mut)}
.pct .val{width:9rem;font-size:.85rem;font-family:"DM Mono",monospace}
.people,.about{display:grid;
 grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr));gap:1.1rem}
.about .card,.people .card{border-top:3px solid var(--accent)}
.about .k,.people .k{color:var(--accent);font-size:.74rem;letter-spacing:.1em;
 text-transform:uppercase;font-weight:700}
.about p,.people p{margin:0;color:var(--mut);font-size:.98rem}
.linkrow{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.8rem}
.linkrow a{font-size:.85rem;color:var(--accent);border:1px solid var(--line);
 border-radius:999px;padding:.25rem .8rem;text-decoration:none}
.linkrow a:hover{border-color:var(--accent)}
.placecard{border:1px dashed var(--line);border-radius:14px;padding:1.2rem;
 color:var(--mut);text-align:center;margin-top:1rem}
details.bngl{background:var(--card);border:1px solid var(--line);
 border-radius:14px;padding:.9rem 1.2rem;margin-top:1rem}
details.bngl summary{cursor:pointer;font-weight:700;color:var(--accent)}
details.bngl pre{font-family:"DM Mono",ui-monospace,monospace;font-size:.8rem;
 line-height:1.45;overflow-x:auto;background:var(--bg);
 border:1px solid var(--line);border-radius:10px;padding:1rem;margin:.8rem 0 0;
 max-height:28rem;overflow-y:auto}
.bib{margin:.5rem 0 0;padding-left:1.2rem}
.bib li{margin:.45rem 0;font-size:.92rem;color:var(--mut)}
.bib b{color:var(--ink);font-weight:500}
footer{margin-top:4rem;padding-top:1.2rem;border-top:1px solid var(--line);
 color:var(--mut);font-size:.85rem}
.scroll{overflow-x:auto}
#usmap [data-fips]{cursor:pointer}

/* the harvested console Methods markup, restyled onto the site's tokens so
   it reads as one page rather than an embedded screenshot of another app */
.methods .card{margin-top:1.2rem}
.methods h2{margin-top:0}
.methods .hint{color:var(--mut);font-size:.9rem}
.methods .fig,.methods figure{margin:1rem 0;overflow-x:auto}
.methods svg{max-width:100%;height:auto;display:block;margin:.6rem auto;
 color:var(--ink)}
.methods svg .svgt-xl{font-size:1.3rem}
.methods svg .svgt-lg{font-size:1rem}
.methods svg .svgt-md{font-size:.92rem}
.methods svg .svgt-sm{font-size:.875rem}
.methods svg .svgt-sub{font-size:.68em}
.methods .figcap,.methods figcaption{color:var(--mut);font-size:.9rem;
 text-align:center;margin-top:.5rem}
.methods table{margin-top:.6rem}
.methods td.ok,.methods .ok{color:var(--ok);font-weight:700}
.methods td.bad,.methods .bad{color:var(--bad);font-weight:700}
.methods .eqpanel,.methods .math{font-family:"DM Mono",ui-monospace,monospace}
.methods .eqpanel{max-width:800px;margin:1rem auto 0;padding:.7rem 1rem;
 background:var(--bg);border:1px solid var(--line);border-radius:10px;
 overflow-x:auto}
.methods .eqnote{font-family:"DM Sans",system-ui,sans-serif;color:var(--mut);
 font-size:.88rem}
@media (max-width:640px){nav.tabs{margin-left:0}.a11y{margin-left:0}}
"""

BOOT = """
(function(){var R=document.documentElement,S=window.localStorage;
 try{['theme','contrast','vision'].forEach(function(k){
   var v=S.getItem('flubnf-site-'+k); if(v)R.setAttribute('data-'+k,v);});}
 catch(e){}})();
"""

JS = r"""
(function(){
  var D = JSON.parse(document.getElementById('flubnf-payload').textContent);
  window.FLUBNF = D;

  // ---- tabs -------------------------------------------------------------
  var tabs = document.getElementById('tabs');
  tabs.addEventListener('click', function(e){
    var b = e.target.closest('button'); if(!b) return;
    tabs.querySelectorAll('button').forEach(function(x){
      x.setAttribute('aria-pressed', x===b ? 'true':'false'); });
    document.querySelectorAll('.page').forEach(function(p){
      p.classList.remove('on'); });
    document.getElementById('p-'+b.dataset.p).classList.add('on');
    window.scrollTo(0,0);
  });

  // ---- outlook model toggle --------------------------------------------
  // The fills were computed server-side by the same usmap code that
  // rendered the map, so a swap can never disagree with what was drawn.
  var OL = D.outlook, MAP = document.getElementById('usmap');
  var mt = document.getElementById('mtoggle');
  function paint(model){
    var f = OL.fills[model]; if(!f || !MAP) return;
    for (var fips in f){
      var p = MAP.querySelector('[data-fips="'+fips+'"]');
      if (p){ p.setAttribute('fill', f[fips].f);
              p.setAttribute('fill-opacity', f[fips].o);
              p.setAttribute('data-hover', f[fips].h); }
    }
    // same sentence the server rendered, so a toggle click cannot quietly
    // restate the coverage the page loaded with
    var lab = document.getElementById('maplabel');
    if (lab) lab.textContent = OL.labels[model] + ' · ' + OL.coverage +
      ' jurisdictions forecast, ' + (OL.mapped != null ? OL.mapped : OL.coverage) +
      ' drawn · ' + OL.source.label;
  }
  if (mt) mt.addEventListener('click', function(e){
    var b = e.target.closest('button'); if(!b) return;
    mt.querySelectorAll('button').forEach(function(x){
      x.setAttribute('aria-pressed', x===b ? 'true':'false'); });
    paint(b.dataset.m);
  });

  // ---- the forecast fan -------------------------------------------------
  var F = D.fans, NAMES = Object.keys(F).sort();
  var sel = document.getElementById('fsel');
  var lock = document.getElementById('flock'), lockRange = null;
  NAMES.forEach(function(s){
    var o = document.createElement('option'); o.textContent = s;
    sel.appendChild(o); });
  function css(t){
    return getComputedStyle(document.documentElement)
             .getPropertyValue(t).trim(); }
  function rgba(hex, a){
    var m = (hex||'').replace('#','');
    if (m.length === 3) m = m[0]+m[0]+m[1]+m[1]+m[2]+m[2];
    if (m.length !== 6) return 'rgba(52,192,240,'+a+')';
    return 'rgba('+parseInt(m.slice(0,2),16)+','+parseInt(m.slice(2,4),16)+
           ','+parseInt(m.slice(4,6),16)+','+a+')'; }
  function draw(name){
    var d = F[name]; if(!d) return;
    var obs = d.obs, last = obs[obs.length-1], hs = ['1','2','3','4'];
    // the forecast x-axis: the settled dates when truth has arrived,
    // otherwise the four weeks after the last observation
    var fx = [last[0]];
    if (d.settled && d.settled.length === 4){
      d.settled.forEach(function(s){ fx.push(s[0]); });
    } else {
      var t = new Date(last[0]+'T00:00:00');
      for (var k=0;k<4;k++){ t.setDate(t.getDate()+7);
        fx.push(t.toISOString().slice(0,10)); }
    }
    var med=[last[1]], lo8=[last[1]], hi8=[last[1]],
        lo5=[last[1]], hi5=[last[1]], pf=[last[1]], an=[last[1]];
    hs.forEach(function(h){
      var q = d.q[h] || {};
      med.push(q['0.5']); lo8.push(q['0.1']); hi8.push(q['0.9']);
      lo5.push(q['0.25']); hi5.push(q['0.75']);
      pf.push(d.pf ? d.pf[h] : null); an.push(d.an ? d.an[h] : null); });
    var ink=css('--ink'), acc=css('--accent'), mut=css('--mut'),
        line=css('--line'), card=css('--card'), gold=css('--gold');
    var T = [
      {x:obs.map(function(o){return o[0];}), y:obs.map(function(o){return o[1];}),
       mode:'lines+markers', name:'observed (as of '+last[0]+')',
       line:{color:ink,width:2}, marker:{size:5},
       hovertemplate:'%{x|%b %e, %Y}<br>%{y:,.0f}<extra>observed</extra>'},
      {x:fx, y:hi8, mode:'lines', line:{width:0}, showlegend:false,
       hoverinfo:'skip'},
      {x:fx, y:lo8, mode:'lines', fill:'tonexty', fillcolor:rgba(acc,.16),
       line:{width:0}, name:'80% interval', hoverinfo:'skip'},
      {x:fx, y:hi5, mode:'lines', line:{width:0}, showlegend:false,
       hoverinfo:'skip'},
      {x:fx, y:lo5, mode:'lines', fill:'tonexty', fillcolor:rgba(acc,.28),
       line:{width:0}, name:'50% interval', hoverinfo:'skip'},
      {x:fx, y:med, mode:'lines+markers', name:'ensemble median',
       line:{color:acc,width:2.5}, marker:{size:6},
       hovertemplate:'%{x|%b %e, %Y}<br>%{y:,.0f}<extra>ensemble median</extra>'}
    ];
    // Member medians are drawn only when the source stored that member,
    // and start hidden: they explain the blend, they are not the forecast.
    if (d.pf) T.push({x:fx, y:pf, mode:'lines', name:'PF-SIHRS median',
      visible:'legendonly', line:{color:'#1979FF',width:1.4}});
    if (d.an) T.push({x:fx, y:an, mode:'lines',
      name:'Calendar analogue median', visible:'legendonly',
      line:{color:gold||'#FFC72C',width:1.4,dash:'dash'}});
    // The settled overlay exists only where truth has arrived. A live
    // forecast has none, so the trace and its legend entry are ABSENT
    // rather than empty, and mid-season it grows a week at a time.
    var st = (d.settled||[]).filter(function(s){ return s[1] != null; });
    if (st.length) T.push({
      x:st.map(function(s){return s[0];}), y:st.map(function(s){return s[1];}),
      mode:'lines+markers', name:'settled outcome',
      line:{color:ink,dash:'dot',width:1.4}, marker:{size:4},
      hovertemplate:'%{x|%b %e, %Y}<br>%{y:,.0f}<extra>what happened</extra>'});
    var fs = parseFloat(getComputedStyle(document.documentElement).fontSize)||16;
    var lay = {
      margin:{l:64,r:16,t:14,b:40}, showlegend:true,
      legend:{orientation:'h', y:-0.16, font:{size:fs*.85, color:mut}},
      paper_bgcolor:card, plot_bgcolor:card, hovermode:'x unified',
      font:{family:'"DM Sans",system-ui,sans-serif', size:fs*.85, color:mut},
      xaxis:{gridcolor:line, zeroline:false, showline:true, linecolor:line},
      yaxis:{gridcolor:line, zeroline:false, rangemode:'tozero',
             tickformat:',d',
             title:{text:'weekly admissions', font:{size:fs*.85}}},
      shapes:[{type:'line', x0:last[0], x1:last[0], yref:'paper', y0:0, y1:1,
               line:{color:mut,width:1,dash:'dash'}}],
      annotations:[{x:last[0], yref:'paper', y:1, text:'forecast date',
                    showarrow:false, xanchor:'right', yanchor:'top',
                    font:{size:fs*.8,color:mut}}]
    };
    if (lock.checked && lockRange) lay.yaxis.range = lockRange;
    Plotly.react('fan', T, lay, {displaylogo:false, responsive:true,
      modeBarButtonsToRemove:['select2d','lasso2d'],
      toImageButtonOptions:{scale:2,
        filename:'flubnf_'+name.replace(/[^A-Za-z0-9]+/g,'_')+'_'+
                 (D.outlook.source.asof||'')}})
      .then(function(gd){
        if(!lock.checked) lockRange = gd._fullLayout.yaxis.range.slice(); });
  }
  function step(d){
    var i = (NAMES.indexOf(sel.value) + d + NAMES.length) % NAMES.length;
    sel.value = NAMES[i]; draw(sel.value); }
  document.getElementById('fprev').addEventListener('click', function(){ step(-1); });
  document.getElementById('fnext').addEventListener('click', function(){ step(1); });
  sel.addEventListener('change', function(){ draw(sel.value); });
  lock.addEventListener('change', function(){ draw(sel.value); });
  sel.value = NAMES.indexOf('Texas') >= 0 ? 'Texas' : NAMES[0];

  // ---- map hover card + click-through to the fan ------------------------
  var HOV = D.outlook.hover, F2N = D.fips_to_name;
  var CATN = {large_decrease:'large decrease', decrease:'decrease',
              stable:'stable', increase:'increase',
              large_increase:'large increase'};
  var TIP = document.createElement('div');
  TIP.style.cssText = 'position:fixed;z-index:60;pointer-events:none;'+
    'display:none;background:var(--card);border:1px solid var(--line);'+
    'border-radius:10px;padding:.55rem .75rem;font-size:.85rem;'+
    'color:var(--ink);box-shadow:0 6px 24px rgba(0,0,0,.35);'+
    'font-family:"DM Sans",system-ui,sans-serif;max-width:16rem';
  document.body.appendChild(TIP);
  if (MAP) MAP.addEventListener('mousemove', function(e){
    var t = e.target.closest('[data-fips]');
    var h = t && HOV[t.getAttribute('data-fips')];
    if(!h){ TIP.style.display='none'; return; }
    var rows = Object.keys(CATN).map(function(k){
      var v = Math.round((h.probs[k]||0)*100);
      return '<div style="display:flex;justify-content:space-between;gap:1rem">'+
             '<span style="color:var(--mut)">'+CATN[k]+'</span><span>'+v+
             '%</span></div>'; }).join('');
    TIP.innerHTML = '<b>'+h.name+'</b><div style="color:var(--mut);'+
      'margin:.15rem 0 .35rem">current '+
      Math.round(h.current).toLocaleString()+' · 1-wk median '+
      Math.round(h.median1).toLocaleString()+'</div>'+rows+
      (F[h.name] ? '<div style="color:var(--accent);margin-top:.35rem;'+
        'font-size:.8rem">click for the full forecast</div>' : '');
    TIP.style.display='block';
    TIP.style.left = Math.min(e.clientX+14, window.innerWidth-260)+'px';
    TIP.style.top  = Math.min(e.clientY+14, window.innerHeight-230)+'px';
  });
  if (MAP) MAP.addEventListener('mouseleave', function(){
    TIP.style.display='none'; });
  if (MAP) MAP.addEventListener('click', function(e){
    var p = e.target.closest('[data-fips]'); if(!p) return;
    var name = F2N[p.getAttribute('data-fips')];
    if (name && F[name]){
      sel.value = name; draw(name);
      document.getElementById('fan').closest('.card')
        .scrollIntoView({behavior:'smooth', block:'center'}); }
  });

  // ---- accessibility pickers -------------------------------------------
  var A = document.getElementById('a11y'), R = document.documentElement;
  function applyA11y(){
    ['theme','contrast','vision'].forEach(function(k){
      var v = null;
      try { v = window.localStorage.getItem('flubnf-site-'+k); } catch(e){}
      if (v) R.setAttribute('data-'+k, v); else R.removeAttribute('data-'+k);
      A.querySelectorAll('[data-k="'+k+'"]').forEach(function(b){
        b.setAttribute('aria-pressed', b.dataset.v===v ? 'true':'false'); });
    });
    draw(sel.value);          // token-coloured chart follows the mode
  }
  A.addEventListener('click', function(e){
    var b = e.target.closest('button'); if(!b) return;
    var k = 'flubnf-site-'+b.dataset.k;
    try {
      var cur = window.localStorage.getItem(k);
      if (cur === b.dataset.v) window.localStorage.removeItem(k);
      else window.localStorage.setItem(k, b.dataset.v);
    } catch(e){}
    applyA11y();
  });
  applyA11y();
  paint(OL.default_model);
})();
"""

CATS = ("large_decrease", "decrease", "stable", "increase", "large_increase")

_MARK = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" '
    'viewBox="0 0 100 100" aria-hidden="true">'
    '<rect width="100" height="100" rx="22" ry="22" fill="#000F7E"/>'
    '<g transform="translate(-2.4,-1.8)">'
    '<path d="M82,27 C 93,44 84,72 63,65" fill="none" stroke="#000F7E" '
    'stroke-width="5.6"/>'
    '<path d="M82,27 C 93,44 84,72 63,65" fill="none" stroke="#FB4653" '
    'stroke-width="3.4"/>'
    '<line x1="65.2" y1="58.4" x2="60.8" y2="71.6" stroke="#000F7E" '
    'stroke-width="5.6" stroke-linecap="round"/>'
    '<line x1="64.9" y1="59.3" x2="61.1" y2="70.7" stroke="#FB4653" '
    'stroke-width="3.4" stroke-linecap="round"/>'
    '<path d="M20,76 C 50,76 50,24 80,24" fill="none" stroke="#34C0F0" '
    'stroke-width="5.0" stroke-linecap="round"/>'
    '<circle cx="20" cy="76" r="5.5" fill="#6E8FD0" stroke="#000F7E" '
    'stroke-width="2.4"/>'
    '<circle cx="50" cy="50" r="6.0" fill="#FFFFFF" stroke="#000F7E" '
    'stroke-width="2.4"/>'
    '<circle cx="80" cy="24" r="5.5" fill="#FFFFFF" stroke="#000F7E" '
    'stroke-width="2.4"/></g></svg>')


def _e(s) -> str:
    return _html.escape(str(s))


def _score_td(v) -> str:
    """One relWIS cell under the app's one relWIS rule: tabular numerals and
    the below-1-beats-baseline colouring, members included. An absent score
    says so instead of printing a dash that reads as zero."""
    if v is None:
        return '<td class="n na">not scored</td>'
    cls = "okc" if float(v) < 1 else "badc"
    return f'<td class="n {cls}">{float(v):.3f}</td>'


def _season_table(payload: dict) -> str:
    seasons = payload["seasons"]
    pooled = payload["pooled"]
    has_official = any("FluSight-ensemble" in s["models"] for s in seasons)
    # The comparator column carries the official FluSight ensemble rather
    # than a constant 1.000 for the baseline: the baseline is already the
    # denominator of every score in the table, so a column of ones restated
    # it, while the hub's own ensemble is a comparator a reader learns from.
    # A season with no official score prints "not scored" rather than a
    # blank that would read as a zero.
    head = ('<tr><th>Season</th><th class="n">Ensemble relWIS</th>'
            '<th class="n">FluSight ensemble</th>'
            '<th class="n">Cells</th><th>FluSight field</th></tr>')

    rows = []
    for s in seasons:
        pl = s.get("placement") or {}
        ens = (s["models"].get("ensemble") or {})
        cells = ens.get("cells")
        r = (f'<tr><td>{_e(s["season"])}</td>'
             + _score_td(ens.get("rel"))
             + _score_td((s["models"].get("FluSight-ensemble")
                          or {}).get("rel")))
        r += f'<td class="n">{cells:,}</td>' if cells else \
             '<td class="n na">--</td>'
        r += (f'<td>{_e(pl["text"])}</td>' if pl.get("text")
              else '<td class="na">not yet scored against the field</td>')
        rows.append(r + "</tr>")

    p = pooled.get("ensemble") or {}
    prow = ('<tr class="total"><td>Pooled</td>' + _score_td(p.get("rel"))
            + _score_td((pooled.get("FluSight-ensemble") or {}).get("rel")))
    prow += (f'<td class="n">{p.get("cells", 0):,}</td>'
             '<td></td></tr>')
    table = "<table>" + head + "".join(rows) + prow + "</table>"

    note = ("Both score columns are relWIS against the same CDC FluSight "
            "baseline, so below 1.000 beats that baseline in either column. "
            "A cell is one location, one forecast week, one horizon, kept "
            "only where settled truth was above zero and the FluSight "
            "baseline also had a forecast.")
    if has_official:
        note += (" The comparator is the official FluSight ensemble, the "
                 "hub's own combination of the forecasts every team "
                 "submitted that week, which makes it a strong reference "
                 "rather than a naive one. It is scored on exactly the "
                 "cells in the ensemble column beside it, so the two "
                 "numbers in a row can be read against each other.")
    return table + ('<p class="sub" style="margin:.9rem 0 0;font-size:.85rem">'
                    + note + "</p>")


_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else _SUFFIX.get(n % 10, "th")
    return str(n) + suffix


def _percentile_bars(payload: dict) -> str:
    rows = []
    for s in payload["seasons"]:
        pl = s.get("placement") or {}
        if pl.get("percentile") is not None:
            rows.append((s["season"], pl["percentile"],
                         pl.get("percentile_text")
                         or _ordinal(pl["percentile"])))
    if not rows:
        return ""
    mean = round(sum(v for _, v, _ in rows) / len(rows))
    out = []
    for label, v, text in rows + [("mean", mean, _ordinal(mean))]:
        out.append(
            f'<div class="pct"><span class="lab">{_e(label)}</span>'
            f'<div class="bar"><div class="fill" style="width:{v}%"></div>'
            f'</div><span class="val">{_e(text)} percentile</span></div>')
    return ('<div style="margin-top:1.2rem">' + "".join(out) + "</div>"
            '<p class="sub" style="margin:.9rem 0 0;font-size:.85rem">'
            "Percentile is the share of the submitting field this ensemble "
            "beat, from the lab's own scoring of the whole FluSight field on "
            "identical cells.</p>")


def _member_table(payload: dict) -> str:
    seasons = payload["seasons"]
    # members first, the blend last as the total row: the table's argument
    # is that the blend beats members that individually take turns losing,
    # and that reads bottom-up
    members = [m for m in payload["model_order"]
               if m != "ensemble" and any(m in s["models"] for s in seasons)]
    if any("ensemble" in s["models"] for s in seasons):
        members.append("ensemble")
    if not members:
        return ""
    labels = {"pf": "PF-SIHRS", "analogue": "Calendar analogue",
              "ensemble": "NAU ensemble", "pf2s": "Two-strain SIHRS"}
    head = ('<tr><th>relWIS by member</th>'
            + "".join(f'<th class="n">{_e(s["season"])}</th>'
                      for s in seasons) + "</tr>")
    rows = []
    for m in members:
        cls = ' class="total"' if m == "ensemble" else ""
        cells = "".join(_score_td((s["models"].get(m) or {}).get("rel"))
                        for s in seasons)
        rows.append(f"<tr{cls}><td>{_e(labels.get(m, m))}</td>{cells}</tr>")
    return "<table>" + head + "".join(rows) + "</table>"


def _consistency_note(payload: dict) -> str:
    checks = payload.get("consistency") or []
    if not checks:
        return ""
    bad = [c for c in checks if not c["ok"]]
    if not bad:
        return ('<p class="sub" style="margin:.9rem 0 0;font-size:.85rem">'
                f"Every one of these {len(checks)} scores was recomputed for "
                "this build from the stored forecasts and matches the figure "
                "the console publishes for the same season.</p>")
    items = "".join(
        f"<li><b>{_e(c['what'])}</b>: this build computed "
        f"{c['computed']:.3f}, the console states {c['app']:.3f}.</li>"
        for c in bad)
    return ('<div class="placecard" style="border-color:var(--bad);'
            'color:var(--bad);text-align:left"><b>Scores disagree with the '
            'console.</b><ul>' + items + "</ul>The numbers above are the ones "
            "computed from the forecasts on disk. Reconcile before "
            "publishing.</div>")


def _bibliography(items) -> str:
    lis = "".join(
        f'<li><b>{_e(i["what"])}.</b> {_e(i["text"])} '
        f'<a href="{_e(i["href"])}">{_e(i["label"])}</a></li>'
        for i in items)
    return f'<ul class="bib">{lis}</ul>'


def render_page(payload: dict, map_svg: str, methods_html: str,
                bibliography, bngl: dict) -> str:
    """Assemble the single page. `payload` is embedded verbatim as the same
    bytes written to site.json, so the file beside the page and the data the
    page reads cannot drift; test_site_build asserts the equality."""
    ol = payload["outlook"]
    src = ol["source"]
    n_loc = len(payload["fans"])
    seasons = payload["seasons"]
    pooled_ens = (payload["pooled"].get("ensemble") or {}).get("rel")

    data_json = json.dumps(payload, indent=1, sort_keys=True,
                           ensure_ascii=False)

    legend = "".join(
        f'<span><span class="sw" style="background:var(--cat-'
        f'{c.replace("_", "-")})"></span>{c.replace("_", " ")}</span>'
        for c in CATS)
    legend += ('<span><span class="sw" style="background:var(--map-nodata)">'
               "</span>no data</span>")

    mbuttons = "".join(
        f'<button data-m="{_e(m)}" aria-pressed='
        f'"{"true" if m == ol["default_model"] else "false"}">'
        f'{_e(ol["labels"][m])}</button>' for m in ol["models"])

    tally = ol.get("modal_tally") or {}
    if tally:
        parts = [f"{n} {k.replace('_', ' ')}" for k, n in tally.items()]
        tally_line = "Most likely category this week: " + \
            ", ".join(parts) + "."
    else:
        tally_line = ""

    # said out loud rather than smoothed over: the forecast covers
    # jurisdictions the Albers map has no shape for
    unmapped = ol.get("unmapped") or []
    if unmapped:
        tally_line += (" " + " and ".join(unmapped) +
                       (" is" if len(unmapped) == 1 else " are") +
                       " forecast but ha" +
                       ("s" if len(unmapped) == 1 else "ve") +
                       " no shape on this projection; use the location "
                       "picker below to see " +
                       ("its" if len(unmapped) == 1 else "their") +
                       " forecast.")

    if src["kind"] == "run":
        prov = (f'made {_e(src["asof"])} by run {_e(src["run_id"])} '
                "&middot; live weekly forecast")
        badge = f'this week &middot; <b>{_e(src["asof"])}</b>'
    else:
        prov = (f'made {_e(src["asof"])} &middot; observations: '
                f'{_e(src.get("observations", "as archived"))} '
                f'&middot; {_e(src["season"])} {_e(src["origin"])}')
        badge = f'week of <b>{_e(src["asof"])}</b>'

    # the settled overlay is conditional, so the sentence describing it has
    # to be too: "all four weeks", "some weeks" and "none yet" are three
    # different claims and only one of them is true of any given build
    counts = [len(f.get("settled") or []) for f in payload["fans"].values()]
    lo, hi = (min(counts), max(counts)) if counts else (0, 0)
    if lo == hi == 4:
        settled_line = ("All four target weeks have settled everywhere, so "
                        "each fan carries the outcome it was scored against.")
    elif hi == 0:
        settled_line = ("No target week has settled yet, so no fan carries a "
                        "settled overlay.")
    elif lo == hi:
        settled_line = (f"{lo} of the four target weeks have settled; the "
                        "overlay stops where truth does.")
    else:
        settled_line = (f"Between {lo} and {hi} of the four target weeks have "
                        "settled, depending on the location; the overlay is "
                        "drawn only for the weeks that have landed.")

    span = ""
    if seasons:
        span = (f'{_e(seasons[0]["season"])} to '
                f'{_e(seasons[-1]["season"])}' if len(seasons) > 1
                else _e(seasons[0]["season"]))

    if pooled_ens is not None and seasons:
        headline = (
            f"Across {len(seasons)} replayed season"
            f"{'s' if len(seasons) != 1 else ''} ({span}) the submitted "
            f"ensemble scores a pooled relWIS of "
            f'<b>{pooled_ens:.3f}</b> against the CDC FluSight baseline. '
            "Below 1 beats it.")
    else:
        headline = ("No season has been scored yet. The table fills in as "
                    "retrospectives complete.")

    standing = (
        '<div class="banner standing"><span class="k">Live standing</span>'
        "&nbsp; " + headline + " Placement among all submitting teams is "
        "not currently published: the earlier standings were withdrawn "
        "because the scorer that produced them does not survive. See the "
        "release record.</div>")

    replay_note = (
        '<div class="placecard">Each settled season is replayable in the '
        "console's season player: the weekly outlook map and the "
        "probabilistic forecast, week by week with the settled truth "
        "overlaid, and the live table of weekly and cumulative relWIS. This "
        "page publishes the finished scores; the player publishes the "
        "path.</div>")

    build = payload["build"]
    versions = ", ".join(f"{k} {v}" for k, v in build["versions"].items()
                         if k in ("pybnf", "bngsim", "bionetgen"))

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FluBNF</title>
<meta name="description" content="Weekly US influenza hospital-admission
 forecasts from the Posner Lab at Northern Arizona University: a mechanistic
 SIHRS model and a calendar analogue, blended and scored on vintage data.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&family=DM+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<script>{BOOT}</script>
</head><body>

<header class="site">
  <span class="brandrow">{_MARK}<span class="wordmark"><em>Flu</em>BNF</span></span>
  <nav class="tabs" id="tabs" aria-label="Sections">
    <button data-p="home" aria-pressed="true">Home</button>
    <button data-p="retro" aria-pressed="false">Retrospectives</button>
    <button data-p="methods" aria-pressed="false">Methods</button>
  </nav>
  <div class="a11y" id="a11y" role="group" aria-label="Display preferences">
    <button data-k="theme" data-v="light">Light</button>
    <button data-k="theme" data-v="dark">Dark</button>
    <button data-k="contrast" data-v="high">Contrast</button>
    <button data-k="vision" data-v="cvd">CV safe</button>
  </div>
</header>
<main>

<div class="page on" id="p-home">
  <div class="banner"><b>FluBNF</b> forecasts weekly US influenza hospital
  admissions for every reporting jurisdiction: a mechanistic transmission
  model and a calendar analogue, blended with equal weights and scored only
  on the data that existed on each forecast date. Click any state for its
  full probabilistic forecast.</div>

  <div class="maphero">
    <div class="maptop">
      <span class="datebadge">{badge}</span>
      <div class="mtoggle" id="mtoggle" role="group" aria-label="Outlook model">
        {mbuttons}
      </div>
    </div>
    {map_svg}
    <div class="legend">{legend}
      <span class="asof" id="maplabel">{_e(ol["labels"][ol["default_model"]])}
       &middot; {ol["coverage"]} jurisdictions forecast, {ol.get("mapped", ol["coverage"])} drawn
       &middot; {_e(src["label"])}</span>
    </div>
    <p class="sub" style="margin:.7rem 0 0;font-size:.88rem">{_e(tally_line)}
    Each state is coloured by its most likely change category and shaded by
    how likely that category is; hover for the full distribution.</p>
  </div>

  {standing}

  <section>
    <div class="kick">Probabilistic forecast</div>
    <p class="sub">The observed weeks behind the forecast date, then the
    ensemble's next four as a median with 50% and 80% intervals, from the
    same forecast week. The CDC submission carries this at 23 quantile
    levels for every jurisdiction, every week. {settled_line}</p>
    <div class="card">
      <div class="fpick">
        <button id="fprev" aria-label="previous location">&#9664;</button>
        <select id="fsel" aria-label="location"></select>
        <button id="fnext" aria-label="next location">&#9654;</button>
        <label style="display:flex;align-items:center;gap:.35rem;
         font-size:.88rem;color:var(--mut)">
          <input type="checkbox" id="flock"> lock axes</label>
      </div>
      <p class="prov">{prov} &middot; {n_loc} locations</p>
      <div id="fan" style="width:100%;height:420px"></div>
    </div>
  </section>

  <section>
    <div class="kick">About us</div>
    <div class="people">
      <div class="card"><span class="k">Lead</span>
        <h3>Ely F. Miller</h3>
        <p>PhD student in Biological Sciences and research lead in the Posner
        Lab, Northern Arizona University. Works across mechanistic epidemic
        modeling, Bayesian inference and uncertainty quantification,
        sequential Monte Carlo and MCMC methods, rule-based simulation, and
        high-performance computing. Builds and operates FluBNF end to end:
        the SIHRS model and its priors, the particle-filter fitting, the
        validation record, and the weekly CDC submissions.</p>
        <div class="linkrow"><a href="https://github.com/elyfmiller">GitHub</a>
        <a href="https://orcid.org/0000-0003-3480-8377">ORCID</a></div></div>
      <div class="card"><span class="k">Lab</span>
        <h3>The Posner Lab</h3>
        <p>Computational systems biology at Northern Arizona University, led
        by Dr. Richard Posner. The lab co-developed PyBioNetFit (Mitra et
        al., iScience 2019) and builds fitting infrastructure used well
        beyond epidemiology. Its forecasting lineage runs through the Los
        Alamos C-model COVID-19 team: real-time pandemic forecasts built
        with LANL collaborators and shared with public health officials.</p>
        </div>
      <div class="card"><span class="k">Software</span>
        <h3>We build our own stack</h3>
        <p>The model is written as rules in BNGL, compiled by BioNetGen,
        integrated by BNGsim (our C++17 engine), and fitted by our
        particle-filter extension of PyBioNetFit, the framework this lab
        co-developed with Los Alamos. Nothing under the hood is a black box
        we cannot open: when a forecast needs a capability, we write it into
        the same open tools everyone else can use. Methods breaks each layer
        down.</p>
        <div class="linkrow">
          <a href="https://github.com/lanl/PyBNF">PyBNF</a>
          <a href="https://pypi.org/project/bngsim/">BNGsim</a>
          <a href="https://bionetgen.org">BioNetGen</a>
        </div></div>
    </div>
  </section>
</div>

<div class="page" id="p-retro">
  <section style="margin-top:1rem">
    <div class="kick">Measured performance</div>
    <p class="sub">Every season re-run week by week on the data archived at
    each forecast date. relWIS below 1 beats the CDC FluSight baseline's own
    submitted forecasts. Each score is recomputed for this build from the
    stored forecasts, never copied from a note.</p>
    <div class="card scroll">
      {_season_table(payload)}
      {_percentile_bars(payload)}
      {_consistency_note(payload)}
    </div>
  </section>

  <section>
    <div class="kick">Season replays</div>
    <p class="sub">The members alternate in strength season to season; the
    equal-weight blend is the forecast we submit. That asymmetry is the
    ensemble's whole argument.</p>
    <div class="card scroll">
      {_member_table(payload)}
    </div>
    {replay_note}
  </section>

  <section>
    <div class="kick">Reproducibility</div>
    <div class="about">
      <div class="card"><span class="k">Data</span>
        <h3>Vintage-true, downloadable</h3>
        <p>Every retrospective number on this page was computed from the
        target file as it existed on that forecast date; revisions arriving
        later never flatter a score. The console's vintage browser shows
        exactly what any past week knew.</p>
        <div class="linkrow">
          <a href="https://github.com/cdcepi/FluSight-forecast-hub/tree/main/target-data">NHSN target data</a>
          <a href="https://github.com/cdcepi/FluSight-forecast-hub">FluSight hub</a>
        </div></div>
      <div class="card"><span class="k">Run it</span>
        <h3>On your own laptop</h3>
        <p>Clone the repository, run the setup script, and the console
        replays any season on macOS, Linux, or Windows, with pause, resume,
        and a playback player for the results.</p>
        <div class="linkrow">
          <a href="https://github.com/elyfmiller/flubnf">Repository</a>
          <a href="https://github.com/elyfmiller/flubnf/blob/main/docs/WINDOWS.md">Windows guide</a>
        </div></div>
      <div class="card"><span class="k">Provenance</span>
        <h3>What produced this page</h3>
        <p>Built from commit <span class="mono">{_e(build["sha"])}</span> on
        {_e(payload["generated_utc"])}, from
        {" and ".join(_e(s["origin"]) for s in seasons) or "no season"}
        data under the console's own state. Engines: {_e(versions)}.</p>
        </div>
    </div>
  </section>
</div>

<div class="page" id="p-methods">
  <section style="margin-top:1rem">
    <div class="kick">How it works</div>
    <p class="sub">This section is rendered from the console's own Methods
    page at build time, diagrams included, so the site and the software it
    describes cannot drift apart.</p>
    <div class="methods">{methods_html}</div>

    <details class="bngl"><summary>View the production model source (BNGL,
      {bngl["lines"]} lines)</summary>
      <p class="sub" style="font-size:.85rem;margin:.5rem 0 0">Tokens in
      double braces are filled per state and week at run time: population,
      initial conditions, and the data-derived pins. This is the exact file
      the fits consume, read from
      <span class="mono">{_e(bngl["path"])}</span>.</p>
      <pre>{_e(bngl["source"])}</pre></details>

    <div class="card" style="margin-top:1rem">
      <span class="k" style="color:var(--accent);font-size:.74rem;
       letter-spacing:.1em;text-transform:uppercase;font-weight:700">Sources</span>
      <h3>Fixed parameters are cited, not chosen</h3>
      <p class="sub" style="margin:0">Every non-fitted value traces to
      literature or to the FluSight hub's own data. These citations are read
      from the module that defines the priors, so a re-sourced parameter
      updates here at the next build.</p>
      {_bibliography(bibliography)}
    </div>
  </section>
</div>

<footer>
  Built {_e(payload["generated_utc"])} from the lab's own retrospectives at
  commit <span class="mono">{_e(build["sha"])}</span>. The console, the
  validation record and this generator live at
  <a href="https://github.com/elyfmiller/flubnf">github.com/elyfmiller/flubnf</a>
  &middot; forecasts target the
  <a href="https://github.com/cdcepi/FluSight-forecast-hub">CDC FluSight hub</a>.
  The data behind this page is the file <span class="mono">site.json</span>
  beside it.
</footer>
</main>

<script type="application/json" id="flubnf-payload">{data_json}</script>
<script src="plotly.min.js"></script>
<script>{JS}</script>
</body></html>
"""
