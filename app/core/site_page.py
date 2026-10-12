"""PUBLIC SITE: how the site looks (site_build.build).

The public site's HTML: one page, three tabs, no network but the fonts.

site_build decides WHAT is true; this module holds all of the page's markup,
CSS and behaviour, so the design is reviewable in one file. Constraints,
each tested:

  * OFFLINE FROM DISK: every asset inline or a sibling file (Google Fonts
    degrades to the system stack).
  * PLOTLY IS A SIBLING (site/plotly.min.js), not 4.9 MB inlined into every
    diff.
  * NO UNRESOLVED PLACEHOLDERS: missing state is omitted with a stated
    reason, never an empty cell, a dash, or an invented number.
  * THEME-AWARE AND ACCESSIBLE: light/dark tokens, high contrast, a
    CVD-safe map scale, persisted like the console's controls.

  1. CSS, BOOT and JS (the page's stylesheet, theme boot and behaviour)
  2. the brand mark and page_scripts
  3. fragments: _season_table, _percentile_bars, _member_table,
     _consistency_note, _bibliography
  4. render_page (the whole page)
"""
from __future__ import annotations

import json

from app.core import horizons as hz, relwis
from app.core.html_page import esc as _e
from app.core.usmap import CATS  # the map's category scale, one source

# ------------------------------------------------------ 1. CSS, BOOT, JS
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
.methods .eqvars{margin-top:.6rem}
.methods .eqvars summary{font-family:"DM Sans",system-ui,sans-serif;
 font-weight:600;cursor:pointer}
.methods .eqvars td{font-family:"DM Sans",system-ui,sans-serif;font-size:.88rem;
 vertical-align:top}
.methods .eqvars tbody th{text-align:left;white-space:nowrap;vertical-align:top}
/* the console's UI kit without its sheet or script: no inert "?" or "i"
   buttons; each tip's text reads under what it explains; the stepper's
   marks give way to the list's own numbers; swatches drawn; text meant
   for screen readers stays hidden */
.methods .tipbtn,.methods .uk-tt-btn,.methods .uk-step-mark{display:none}
.methods .tipbox,.methods .uk-tt-pop{display:block;color:var(--mut);
 font-size:.9rem;font-weight:400}
.methods .uk-tt-line,.methods .uk-tt-title{display:block}
.methods .uk-heading{margin-bottom:.4rem}
.methods .uk-stat{display:flex;flex-wrap:wrap;align-items:baseline;
 gap:.1rem .5rem;margin:.35rem 0}
.methods .uk-stat dt{display:contents;font-weight:600}
.methods .uk-stat dd{margin:0}
.methods .uk-stat .tip{order:3;flex-basis:100%}
.methods .uk-stat-u{color:var(--mut)}
.methods .uk-legend{list-style:none;display:flex;flex-wrap:wrap;
 gap:.3rem 1rem;padding:0;margin:.4rem 0}
.methods .uk-sw{display:inline-block;width:.8em;height:.8em;margin-right:.3em;
 border-radius:2px;background:var(--sw)}
.methods .uk-tag{color:var(--mut);font-size:.85rem;font-weight:600}
.methods .uk-sr{position:absolute;width:1px;height:1px;overflow:hidden;
 clip:rect(0 0 0 0);white-space:nowrap}
.methods svg.uk-icon{display:inline-block;width:1em;height:1em;margin:0;
 vertical-align:-.125em}
/* the record card: the pooled figures lead, the convention waits behind
   a disclosure */
.standing .figs{display:flex;flex-wrap:wrap;gap:.6rem 2.2rem;margin:.6rem 0 .5rem}
.standing .fig{display:flex;flex-direction:column}
.standing .fv{font-family:"DM Mono",ui-monospace,monospace;font-size:1.9rem;
 font-weight:500;line-height:1.15}
.standing .fl{color:var(--mut);font-size:.85rem}
.standing p{margin:.2rem 0 0;font-size:.95rem}
.standing details{margin-top:.6rem;font-size:.88rem;color:var(--mut)}
.standing summary{cursor:pointer;color:var(--accent);font-weight:600}
.standing details p{font-size:.88rem}
.alarm{border:1px solid var(--bad);color:var(--bad);border-radius:14px;
 padding:1rem 1.2rem;margin-top:1rem;background:var(--card)}
.alarm ul{margin:.4rem 0}
/* the map: capped on wide screens, its legend beside it */
.mapgrid{display:block}
.mapgrid .mapbox{width:100%;max-width:50rem;margin:0 auto}
@media (min-width:1000px){
 .mapgrid{display:grid;grid-template-columns:minmax(0,50rem) 11rem;
  gap:2rem;justify-content:center;align-items:center}
 .mapgrid .legend{flex-direction:column;align-items:flex-start;gap:.45rem;
  margin:0 0 1rem}
}
#fan{width:100%;height:420px}
.cumlegend{display:flex;flex-wrap:wrap;gap:.4rem 1.2rem;font-size:.85rem;
 color:var(--mut);margin-bottom:.4rem}
.cumlegend .ln{display:inline-block;width:1.4em;height:0;vertical-align:.3em;
 margin-right:.4em;border-top:2px solid}
.cumgrid{display:grid;gap:1rem;
 grid-template-columns:repeat(auto-fit,minmax(min(100%,19rem),1fr))}
.cumgrid h3{font-size:1rem;margin:0 0 .2rem}
.cumchart{width:100%;height:220px}
.dl{font-size:.85rem}
@media (max-width:640px){nav.tabs{margin-left:0}.a11y{margin-left:0}
 #fan{height:320px}}
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
  // the fan's mechanistic median, named for what the source stored
  var FANNAME = ((D.outlook && D.outlook.source && D.outlook.source.pf_label)
                 || 'Oracle SIHRS') === 'Oracle SIHRS'
                ? 'Oracle SIHRS' : 'particle filter';
  window.FLUBNF = D;
  // phones: no Plotly toolbar over the chart, a two-column legend
  var NARROW = !!(window.matchMedia &&
                  window.matchMedia('(max-width:640px)').matches);
  function PLT(){ return window.FluCharts || Plotly; }

  // ---- the address: #retro, #methods or #fan=<location> ----------------
  function setHash(h){
    try { history.replaceState(null, '', h ? '#'+h
                               : location.href.split('#')[0]); }
    catch(e){ if (h) location.hash = h; }
  }

  // ---- tabs -------------------------------------------------------------
  var tabs = document.getElementById('tabs');
  function showTab(p){
    var b = tabs.querySelector('button[data-p="'+p+'"]'); if(!b) return;
    tabs.querySelectorAll('button').forEach(function(x){
      x.setAttribute('aria-pressed', x===b ? 'true':'false'); });
    document.querySelectorAll('.page').forEach(function(pg){
      pg.classList.remove('on'); });
    document.getElementById('p-'+p).classList.add('on');
    if (p === 'retro') drawCum();    // sized only once the tab is visible
  }
  tabs.addEventListener('click', function(e){
    var b = e.target.closest('button'); if(!b) return;
    showTab(b.dataset.p);
    setHash(b.dataset.p === 'home' ? '' : b.dataset.p);
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
    var obs = d.obs, last = obs[obs.length-1], hs = __HORIZONS__;
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
        lo5=[last[1]], hi5=[last[1]], an=[last[1]];
    hs.forEach(function(h){
      var q = d.q[h] || {};
      med.push(q['0.5']); lo8.push(q['0.1']); hi8.push(q['0.9']);
      lo5.push(q['0.25']); hi5.push(q['0.75']);
      an.push(d.an ? d.an[h] : null); });
    var ink=css('--ink'), acc=css('--accent'), mut=css('--mut'),
        line=css('--line'), card=css('--card'), gold=css('--gold');
    var T = [
      {x:obs.map(function(o){return o[0];}), y:obs.map(function(o){return o[1];}),
       mode:'lines+markers', name:NARROW ? 'observed' : 'observed (as of '+last[0]+')',
       line:{color:ink,width:2}, marker:{size:5},
       hovertemplate:'%{x|%b %e, %Y}<br>%{y:,.0f}<extra>observed</extra>'},
      {x:fx, y:hi8, mode:'lines', line:{width:0}, showlegend:false,
       hoverinfo:'skip'},
      {x:fx, y:lo8, mode:'lines', fill:'tonexty', fillcolor:rgba(acc,.16),
       line:{width:0}, name:NARROW ? '80%' : '80% interval', hoverinfo:'skip'},
      {x:fx, y:hi5, mode:'lines', line:{width:0}, showlegend:false,
       hoverinfo:'skip'},
      {x:fx, y:lo5, mode:'lines', fill:'tonexty', fillcolor:rgba(acc,.28),
       line:{width:0}, name:NARROW ? '50%' : '50% interval', hoverinfo:'skip'},
      {x:fx, y:med, mode:'lines+markers', name:NARROW ? (FANNAME === 'Oracle SIHRS' ? 'Oracle' : 'filter') + ' median' : FANNAME+' median',
       line:{color:acc,width:2.5}, marker:{size:6},
       hovertemplate:'%{x|%b %e, %Y}<br>%{y:,.0f}<extra>'+FANNAME+' median</extra>'}
    ];
    // The Groundhog's median is drawn when the source stored it: it is
    // the other submission, on the same axes (the legend toggles it).
    if (d.an) T.push({x:fx, y:an, mode:'lines',
      name:NARROW ? 'Groundhog' : 'Groundhog median',
      line:{color:gold||'#FFC72C',width:1.8,dash:'dash'},
      hovertemplate:'%{x|%b %e, %Y}<br>%{y:,.0f}<extra>Groundhog median</extra>'});
    // The settled overlay exists only where truth has arrived. A live
    // forecast has none, so the trace and its legend entry are ABSENT
    // rather than empty, and mid-season it grows a week at a time.
    var st = (d.settled||[]).filter(function(s){ return s[1] != null; });
    if (st.length) T.push({
      x:st.map(function(s){return s[0];}), y:st.map(function(s){return s[1];}),
      mode:'lines+markers', name:NARROW ? 'settled' : 'settled outcome',
      line:{color:ink,dash:'dot',width:1.4}, marker:{size:4},
      hovertemplate:'%{x|%b %e, %Y}<br>%{y:,.0f}<extra>what happened</extra>'});
    var fs = parseFloat(getComputedStyle(document.documentElement).fontSize)||16;
    var lay = {
      margin:{l:64,r:16,t:14,b:40}, showlegend:true,
      legend:NARROW
        ? {orientation:'h', y:-0.12, x:0, font:{size:fs*.75, color:mut}}
        : {orientation:'h', y:-0.16, font:{size:fs*.85, color:mut}},
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
    // FluCharts (charts.js, inlined below plotly): Saturday week ticks,
    // refit after zoom, pan and resize, like the console and the reports
    // phones: short legend names, no y title (the sentence above names it)
    if (NARROW){ lay.margin = {l:44,r:8,t:14,b:40}; lay.yaxis.title = null; }
    var cfg = {displaylogo:false, responsive:true,
      modeBarButtonsToRemove:['select2d','lasso2d'],
      toImageButtonOptions:{scale:2,
        filename:'flubnf_'+name.replace(/[^A-Za-z0-9]+/g,'_')+'_'+
                 (D.outlook.source.asof||'')}};
    if (NARROW) cfg.displayModeBar = false;
    var PL = window.FluCharts || Plotly;
    PL.react('fan', T, lay, cfg)
      .then(function(gd){
        if(!lock.checked) lockRange = gd._fullLayout.yaxis.range.slice(); });
  }
  function pick(name){
    sel.value = name; draw(name);
    setHash('fan=' + encodeURIComponent(name)); }
  function step(d){
    var i = (NAMES.indexOf(sel.value) + d + NAMES.length) % NAMES.length;
    pick(NAMES[i]); }
  document.getElementById('fprev').addEventListener('click', function(){ step(-1); });
  document.getElementById('fnext').addEventListener('click', function(){ step(1); });
  sel.addEventListener('change', function(){ pick(sel.value); });
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
        'font-size:.8rem">tap or click for the full forecast</div>' : '');
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
      // a tap fires mousemove too: the card would stay over the fan
      TIP.style.display = 'none';
      pick(name);
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
    if (document.getElementById('p-retro').classList.contains('on'))
      drawCum();
  }

  // ---- cumulative relWIS, one small chart per season --------------------
  function drawCum(){
    var boxes = document.querySelectorAll('[data-cum]');
    if (!boxes.length) return;
    var acc=css('--accent'), mut=css('--mut'),
        line=css('--line'), card=css('--card');
    var fs = parseFloat(getComputedStyle(document.documentElement).fontSize)||16;
    var BY = {}, MODELS = [], lo = 1, hi = 1;
    // one y range for every season, so the small multiples compare
    D.seasons.forEach(function(s){ BY[s.season] = s;
      (s.weekly || []).forEach(function(w){
        for (var k in (w.cum || {})){
          if (!{pf:1, analogue:1, ensemble:1}[k]) continue;
          lo = Math.min(lo, w.cum[k]); hi = Math.max(hi, w.cum[k]); } }); });
    var pad = (hi - lo) * 0.06 || 0.05;
    try { MODELS = JSON.parse(
      document.getElementById('cumgrid').getAttribute('data-members')); }
    catch(e){}
    MODELS.forEach(function(m){ m[2] = css(m[2]) || acc; });
    Array.prototype.forEach.call(boxes, function(el){
      var s = BY[el.getAttribute('data-cum')];
      if (!s || !s.weekly || !s.weekly.length) return;
      var x = s.weekly.map(function(w){ return w.asof; });
      var T = [{x:[x[0], x[x.length-1]], y:[1, 1], mode:'lines',
                name:'CDC baseline', hoverinfo:'skip',
                line:{color:mut, width:1, dash:'dot'}}];
      MODELS.forEach(function(m){
        var y = s.weekly.map(function(w){
          var v = (w.cum || {})[m[0]]; return v == null ? null : v; });
        var any = y.some(function(v){ return v != null; });
        if (any) T.push({x:x, y:y, mode:'lines', name:m[1],
          line:{color:m[2], width:2, dash:m[3]},
          hovertemplate:'%{x|%b %e, %Y}<br>%{y:.3f}<extra>'+m[1]+'</extra>'});
      });
      var lay = {margin:{l:44,r:10,t:8,b:28}, showlegend:false,
        paper_bgcolor:card, plot_bgcolor:card, hovermode:'x unified',
        font:{family:'"DM Sans",system-ui,sans-serif', size:fs*.75, color:mut},
        xaxis:{gridcolor:line, zeroline:false, showline:true, linecolor:line},
        yaxis:{gridcolor:line, zeroline:false, tickformat:'.2f',
               range:[lo - pad, hi + pad]}};
      PLT().react(el, T, lay, {displaylogo:false, responsive:true,
                               displayModeBar:false});
    });
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

  // ---- open where the address points ----------------------------------
  (function(){
    var h = '';
    try { h = decodeURIComponent((location.hash || '').slice(1)); } catch(e){}
    if (h === 'retro' || h === 'methods') { showTab(h); return; }
    if (h.indexOf('fan=') === 0 && F[h.slice(4)]){
      sel.value = h.slice(4); draw(sel.value);
      document.getElementById('fan').closest('.card')
        .scrollIntoView({block:'center'});
    }
  })();
})();
""".replace("__HORIZONS__", json.dumps(list(hz.HORIZONS)))
# the fan reads site_build's canonical keys; app.core.horizons owns them

# ------------------------------------------------ 2. the mark and scripts
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


def page_scripts() -> str:
    """The page's scripts: plotly.js (the file beside the page), then the
    shared date-axis helper (charts.js, inlined as the reports inline it,
    so the fan ticks on the data's Saturdays), then the page's own."""
    from app.core.html_page import charts_js
    return ('<script src="plotly.min.js"></script>\n'
            f'<script>{charts_js()}</script>\n<script>{JS}</script>')


# ------------------------------------------------------------ 3. fragments
def _score_td(v) -> str:
    """One relWIS cell under the app's one relWIS rule: tabular numerals and
    the below-1-beats-baseline colouring, members included. An absent score
    says so instead of printing a dash that reads as zero."""
    if v is None:
        return '<td class="n na">not scored</td>'
    cls = "okc" if float(v) < 1 else "badc"
    return f'<td class="n {cls}">{float(v):.3f}</td>'


#: the largest pooled gap the panel may call "level": a fixed threshold (no
#: test runs at build time), inside the sealed record's week-clustered
#: bootstrap interval (half-width ~0.05); wider gaps withhold the sentence
LEVEL_GAP = 0.02


def _season_table(payload: dict) -> str:
    seasons = payload["seasons"]
    pooled = payload["pooled"]
    has_official = any("FluSight-ensemble" in s["models"] for s in seasons)
    # comparator: the FluSight ensemble (the baseline is already every
    # score's denominator); each column named for whose forecast it scores
    pf_name = payload.get("pf_label") or "Oracle SIHRS"
    head = ('<tr><th>Season</th><th class="n">' + _e(pf_name) + '</th>'
            '<th class="n">Groundhog</th>'
            '<th class="n">FluSight Ensemble</th>'
            '<th class="n">Cells</th></tr>')

    rows = []
    for s in seasons:
        pf = (s["models"].get("pf") or {})
        gh = (s["models"].get("analogue") or {})
        cells = pf.get("cells") or gh.get("cells")
        r = (f'<tr><td>{_e(s["season"])}</td>'
             + _score_td(pf.get("rel"))
             + _score_td(gh.get("rel"))
             + _score_td((s["models"].get("FluSight-ensemble")
                          or {}).get("rel")))
        r += f'<td class="n">{cells:,}</td>' if cells else \
             '<td class="n na">not scored</td>'
        rows.append(r + "</tr>")

    p = pooled.get("pf") or {}
    pg = pooled.get("analogue") or {}
    prow = ('<tr class="total"><td>Pooled</td>' + _score_td(p.get("rel"))
            + _score_td(pg.get("rel"))
            + _score_td((pooled.get("FluSight-ensemble") or {}).get("rel")))
    prow += (f'<td class="n">{(p.get("cells") or pg.get("cells") or 0):,}'
             '</td></tr>')
    table = "<table>" + head + "".join(rows) + prow + "</table>"

    # name the convention here too (imported, never retyped)
    note = ("Every column is relWIS against the same CDC FluSight baseline "
            "on the same cells, so lower is better and below 1.000 beats "
            "that baseline. " + relwis.PUBLISHED_CONVENTION_NOTE)
    if has_official:
        note += (" The comparator is the hub's own combination of every "
                 "team's forecasts, a strong reference rather than a naive "
                 "one.")
        # computed, not typed; withheld when the gap exceeds LEVEL_GAP
        off = (pooled.get("FluSight-ensemble") or {}).get("rel")
        # weeks where both the PF and the ensemble scored (not scored_weeks)
        weeks = sum(1 for s in seasons for w in s.get("weekly") or []
                    if "pf" in w.get("week", {})
                    and "FluSight-ensemble" in w.get("week", {}))
        if p.get("rel") is not None and off is not None and weeks:
            gap = abs(p["rel"] - off)
            if gap <= LEVEL_GAP:
                note += (f" Pooled, the PF and the comparator are level: a "
                         f"gap of {gap:.3f} over {weeks} forecast weeks, "
                         "inside the sealed record's measured week-to-week "
                         "variation.")
    if pf_name != "Oracle SIHRS":
        # sealed replays predate the Oracle step: say the column is the plain filter
        note += (" The mechanistic column is the particle filter alone: "
                 "these replays predate the Oracle step, which blends the "
                 "filter's forecast growth with past seasons' at the same "
                 "calendar week. The Oracle step's own record is on the "
                 "Methods tab.")
    # the field column was always withdrawn: said once here, not per row.
    # A restored standing (harvest_placement) is named per season instead.
    placed = [s for s in seasons if (s.get("placement") or {}).get("text")]
    if placed:
        note += " Standing among the FluSight field: " + "; ".join(
            f'{_e(s["season"])} {_e(s["placement"]["text"])}'
            for s in placed) + "."
    else:
        note += (" Standing among the FluSight field: placement withdrawn, "
                 "see Methods for the reason.")
    note += " Methods also carries the donor pool and the two-strain result."
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
            "Percentile is the share of the submitting field this model "
            "beat, from the lab's own scoring of the whole FluSight field on "
            "identical cells.</p>")


#: the console's names (player.js map), so one page never names a model
#: twice; the mechanistic member's comes from the payload's pf_label
_MEMBER_NAMES = {"analogue": "Groundhog",
                 "ensemble": "FluBNF Ensemble (retired)",
                 "pf2s": "Two-strain SIHRS"}
#: each member's line on the cumulative charts: the fan's colours
_MEMBER_STYLE = {"pf": ("--accent", "solid"), "analogue": ("--gold", "dash"),
                 "ensemble": ("--ink", "dot")}


def _cum_charts(payload: dict) -> str:
    """One small chart per season: each member's cumulative relWIS week by
    week (seasons[].weekly[].cum), drawn by the page script when the tab
    opens. The season table above holds the same end points as numbers."""
    seasons = [s for s in payload["seasons"] if s.get("weekly")]
    # the two models in order; an older payload's stored blend last
    members = [m for m in payload["model_order"]
               if m != "ensemble" and any(
                   m in w.get("cum", {}) for s in seasons for w in s["weekly"])]
    if any("ensemble" in w.get("cum", {})
           for s in seasons for w in s["weekly"]):
        members.append("ensemble")
    if not seasons or not members:
        return ""
    names = dict(_MEMBER_NAMES, pf=payload.get("pf_label") or _ORACLE)
    spec = [[m, names.get(m, m)] + list(_MEMBER_STYLE.get(m, ("--mut", "dot")))
            for m in members]
    legend = "".join(
        f'<span><span class="ln" style="border-top-style:'
        f'{"dashed" if st[3] == "dash" else "dotted" if st[3] == "dot" else "solid"};'
        f'border-color:var({st[2]})"></span>{_e(st[1])}</span>'
        for st in spec)
    legend += ('<span><span class="ln" style="border-top:1px dotted '
               'var(--mut)"></span>CDC baseline (1.000)</span>')
    boxes = "".join(
        f'<div><h3>{_e(s["season"])}</h3><div class="cumchart" '
        f'data-cum="{_e(s["season"])}" role="img" aria-label="Cumulative '
        f'relWIS through the {_e(s["season"])} season"></div></div>'
        for s in seasons)
    return (f'<div class="cumlegend">{legend}</div>'
            f'<div class="cumgrid" id="cumgrid" data-members='
            f'"{_e(json.dumps(spec))}">{boxes}</div>')


def _drift_items(bad: list) -> str:
    return "".join(
        f"<li><b>{_e(c['what'])}</b>: this build computed "
        f"{c['computed']:.3f}, the console states {c['app']:.3f}.</li>"
        for c in bad)


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
    return ('<div class="placecard" style="border-color:var(--bad);'
            'color:var(--bad);text-align:left"><b>Scores disagree with the '
            'console.</b><ul>' + _drift_items(bad) + "</ul>The numbers above "
            "are the ones computed from the forecasts on disk. Reconcile "
            "before publishing.</div>")


def _drift_alarm(payload: dict) -> str:
    """The same alarm on Home, above the record, when any check failed."""
    bad = [c for c in payload.get("consistency") or [] if not c["ok"]]
    if not bad:
        return ""
    return ('<div class="alarm" role="alert"><b>Scores disagree with the '
            "console.</b> This build's figures differ from the ones the "
            "console publishes:<ul>" + _drift_items(bad) + "</ul>The "
            "Retrospectives tab prints the figures computed from the "
            "forecasts on disk. Reconcile before publishing.</div>")


def _bibliography(items) -> str:
    lis = "".join(
        f'<li><b>{_e(i["what"])}.</b> {_e(i["text"])} '
        f'<a href="{_e(i["href"])}">{_e(i["label"])}</a></li>'
        for i in items)
    return f'<ul class="bib">{lis}</ul>'


# ------------------------------------------------------------ 4. the page
#: the mechanistic member's two names (site_build.PF_LABEL_ORACLE and
#: PF_LABEL_FILTER); the payload's pf_label says which a build stored
_ORACLE = "Oracle SIHRS"

REPO_URL = "https://github.com/elyfmiller/flubnf"
INSTALL_URL = REPO_URL + "#install-and-run"
RELEASE_URL = REPO_URL + "/blob/main/docs/archive/RELEASE-1.0.md"

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _when(iso: str) -> str:
    """'2026-10-05T18:21:07+00:00' -> '5 October 2026, 18:21 UTC'; anything
    unparseable is printed as given."""
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(str(iso)).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return str(iso)
    return f"{t.day} {_MONTHS[t.month - 1]} {t.year}, {t:%H:%M} UTC"


def _mech(label) -> dict:
    """How the page names the mechanistic member for a pf label: the
    Oracle SIHRS only when the source stored it, else the filter alone,
    so a filter-only build never names the Oracle SIHRS."""
    if (label or _ORACLE) == _ORACLE:
        return {"oracle": True, "name": _ORACLE, "the": "the Oracle SIHRS",
                "plain": _ORACLE,
                "what": ("a mechanistic transmission model fitted each week "
                         "whose forecast growth is blended with past "
                         "seasons' growth at the same calendar week")}
    return {"oracle": False, "name": str(label), "the": "the particle filter",
            "plain": str(label).lower(),
            "what": ("the mechanistic transmission model fitted each week, "
                     "shown here as the particle filter alone: these "
                     "replays predate the Oracle step, which blends its "
                     "forecast growth with past seasons'")}


def _favicon() -> str:
    """The inline mark as a data: URI (no file to ship, nothing remote)."""
    from urllib.parse import quote
    return "data:image/svg+xml," + quote(_MARK, safe=" =:/,.-")


def _standing(payload: dict, mech: dict, span: str) -> str:
    """Home's record card: the pooled figures first, the convention behind
    a disclosure."""
    seasons = payload["seasons"]
    pooled = payload["pooled"]
    figs = []
    for m, name in (("pf", mech["name"]), ("analogue", "Groundhog")):
        v = (pooled.get(m) or {}).get("rel")
        if v is None:
            continue
        cls = "okc" if v < 1 else "badc"
        figs.append(f'<div class="fig"><span class="fv {cls}">{v:.3f}</span>'
                    f'<span class="fl">{_e(name)}, pooled relWIS</span></div>')
    if figs and seasons:
        n = len(seasons)
        lead = (f'<div class="figs">{"".join(figs)}</div><p>Pooled over {n} '
                f'replayed season{"s" if n != 1 else ""} ({span}); below 1 '
                "beats the CDC baseline. Placement among all submitting "
                "teams is not published: the earlier standings were "
                "withdrawn because the scorer that produced them does not "
                f'survive (<a href="{RELEASE_URL}">release record</a>).</p>'
                "<details><summary>How the pooled figure is computed"
                f"</summary><p>{_e(relwis.PUBLISHED_CONVENTION_NOTE)}</p>"
                "</details>")
    else:
        lead = ("<p>No season has been scored yet. The record fills in as "
                "retrospectives complete.</p>")
    return ('<div class="banner standing"><span class="k">Retrospective '
            f"record</span>{lead}</div>")


def render_page(payload: dict, map_svg: str, methods_html: str,
                bibliography, bngl: dict) -> str:
    """Assemble the single page. `payload` is embedded verbatim as the same
    bytes written to site.json, so the file beside the page and the data the
    page reads cannot drift; test_site_build asserts the equality."""
    ol = payload["outlook"]
    src = ol["source"]
    n_loc = len(payload["fans"])
    seasons = payload["seasons"]
    # the seasons' name for the member (banner, record, replays) and the
    # outlook source's (map and fan): each says what its source stored
    mech = _mech(payload.get("pf_label"))
    fan_mech = _mech(src.get("pf_label"))

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

    # the fan's mechanistic median, named for what the source stored
    # (site_build: the member when the run or week carries the Oracle step)
    fan_name = "Oracle SIHRS" if fan_mech["oracle"] else "particle filter"

    tally = ol.get("modal_tally") or {}
    if tally:
        parts = [f"{n} {k.replace('_', ' ')}" for k, n in tally.items()]
        tally_line = "Most likely category this week: " + \
            ", ".join(parts) + "."
    else:
        tally_line = ""

    # name the forecast jurisdictions the Albers map cannot draw
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

    # the sentence matches the overlay: all four, some, or none settled
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

    standing = _standing(payload, mech, span)

    if mech["oracle"]:
        models_line = (f"{mech['the']}, {mech['what']}, and the Groundhog, "
                       "a calendar analogue.")
    else:
        models_line = ("a mechanistic transmission model fitted each week "
                       "and the Groundhog, a calendar analogue. These "
                       "replays show the mechanistic model as the particle "
                       "filter alone, before the Oracle step that blends its "
                       "forecast growth with past seasons'.")
    banner = ("<b>FluBNF</b> forecasts weekly US influenza hospital "
              "admissions for every reporting jurisdiction with two models, "
              "submitted separately: " + models_line + " Both are fitted "
              "only on the data that existed on each forecast date and "
              "scored against settled truth. Tap or click any state for its "
              "full probabilistic forecast.")
    if mech["oracle"]:
        description = (
            "Weekly US influenza hospital-admission forecasts from the "
            "Posner Lab at Northern Arizona University: the Oracle SIHRS, a "
            "mechanistic model whose forecast growth is blended with past "
            "seasons', and the Groundhog, a calendar analogue; submitted "
            "separately and scored on vintage data.")
    else:
        description = (
            "Weekly US influenza hospital-admission forecasts from the "
            "Posner Lab at Northern Arizona University: a mechanistic model "
            "fitted by a particle filter and the Groundhog, a calendar "
            "analogue; submitted separately and scored on vintage data.")

    replay_note = (
        '<div class="placecard">Each settled season replays in the '
        "console's season player: the weekly categorical forecast map and "
        "the probabilistic forecast, week by week with the settled truth "
        "overlaid, and the live table of weekly and cumulative relWIS. The "
        "Groundhog replays on any machine that runs the console; "
        f"{mech['the']} needs the lab's engine (PyBNF, BNGsim and "
        f'BioNetGen). <a href="{INSTALL_URL}">Install and run</a>.</div>')

    build = payload["build"]
    from app.core.site_build import ENGINE_KEYS, engine_version
    engines = [f"{k} {engine_version(build['versions'], k)}"
               for k in ENGINE_KEYS
               if engine_version(build["versions"], k)]
    if engines:
        engine_line = (
            f"Engines: {_e(', '.join(engines))}. Engine versions are "
            "self-reported by the builder's install; the sealed record's "
            "engine pin is bngsim 0.15.1, pinned by every engine installer, "
            "and a locally built engine can self-report an older version "
            "string.")
    else:
        engine_line = ("The sealed record's engine pin is bngsim 0.15.1, "
                       "pinned by every engine installer.")
    built_at = _when(payload["generated_utc"])
    title = "FluBNF: weekly US influenza hospital-admission forecasts"

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title>
<meta name="description" content="{_e(description)}">
<meta property="og:title" content="{_e(title)}">
<meta property="og:description" content="{_e(description)}">
<meta property="og:type" content="website">
<link rel="icon" type="image/svg+xml" href="{_e(_favicon())}">
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
  <div class="banner">{banner}</div>

  {_drift_alarm(payload)}

  <div class="maphero">
    <div class="maptop">
      <span class="datebadge">{badge}</span>
      <div class="mtoggle" id="mtoggle" role="group" aria-label="Categorical forecast model">
        {mbuttons}
      </div>
    </div>
    <div class="mapgrid">
      <div class="mapbox">{map_svg}</div>
      <div class="legend">{legend}</div>
    </div>
    <p class="asof" id="maplabel" style="margin:.6rem 0 0">{_e(ol["labels"][ol["default_model"]])}
     &middot; {ol["coverage"]} jurisdictions forecast, {ol.get("mapped", ol["coverage"])} drawn
     &middot; {_e(src["label"])}</p>
    <p class="sub" style="margin:.5rem 0 0;font-size:.88rem">{_e(tally_line)}
    Each state is coloured by its most likely change category and shaded by
    how likely that category is; tap or hover for the full distribution.</p>
  </div>

  {standing}

  <section>
    <div class="kick">Probabilistic forecast</div>
    <p class="sub">The observed weeks behind the forecast date, then the
    {fan_name}'s next four as a median with 50% and 80% intervals,
    from the same forecast week, with the Groundhog's median as a dashed
    line (the legend toggles any line).
    Each CDC submission carries its model at 23 quantile levels for every
    jurisdiction, every week. {settled_line}</p>
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
      <div id="fan"></div>
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
        the SIHRS compartment model and its priors, the particle-filter
        fitting, the donor-growth (Oracle) step, the
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
    <p class="sub">Both members, every season, re-run week by week on the
    data archived at each forecast date.</p>
    <div class="card scroll">
      {_season_table(payload)}
      {_percentile_bars(payload)}
      {_consistency_note(payload)}
    </div>
  </section>

  <section>
    <div class="kick">Season replays</div>
    <p class="sub">Two models, each submitted on its own: the mechanistic
    {_e(mech["plain"])} and the empirical Groundhog. They fail differently
    season to season, which is why both are filed. Each line is the
    model's relWIS pooled from the season's first forecast week to the week
    shown; below the dotted line at 1 beats the CDC baseline.</p>
    <div class="card">
      {_cum_charts(payload)}
    </div>
    {replay_note}
  </section>

  <section>
    <div class="kick">Reproducibility</div>
    <div class="about">
      <div class="card"><span class="k">Data</span>
        <h3>Vintage-true, downloadable</h3>
        <p>Every forecast on this page was produced from the target file as
        it existed on that forecast date; no model input includes a later
        revision. Scores then use today's settled truth for actuals,
        identically for these models and for the baseline, so revisions
        enter both sides of every ratio the same way. The console's vintage
        browser shows exactly what any past week knew.</p>
        <div class="linkrow">
          <a href="site.json" download>This page's data (site.json)</a>
          <a href="https://github.com/cdcepi/FluSight-forecast-hub/tree/main/target-data">NHSN target data</a>
          <a href="https://github.com/cdcepi/FluSight-forecast-hub">FluSight hub</a>
        </div></div>
      <div class="card"><span class="k">Run it</span>
        <h3>On your own laptop</h3>
        <p>Clone the repository and run the setup script: the console
        replays the Groundhog on macOS, Linux, or Windows, with pause,
        resume, and a playback player for the results. {_e(mech["the"][0].upper() + mech["the"][1:])}
        also needs the lab's engine, which the engine installer sets up.</p>
        <div class="linkrow">
          <a href="{INSTALL_URL}">Install and run</a>
          <a href="{REPO_URL}">Repository</a>
          <a href="{REPO_URL}/blob/main/docs/WINDOWS.md">Windows guide</a>
        </div></div>
      <div class="card"><span class="k">Provenance</span>
        <h3>What produced this page</h3>
        <p>Built from commit <span class="mono">{_e(build["sha"])}</span> on
        {_e(built_at)}, from
        {" and ".join(dict.fromkeys(_e(s["origin"]) for s in seasons)) or "no season"}
        data under the console's own state. {engine_line}</p>
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
      <h3>Sourced where sourced, and said plainly where not</h3>
      <p class="sub" style="margin:0">The recovery rate and the data-derived
      values below carry citations; three fixed values (the admission
      fraction, the discharge rate, and immune waning) are working
      assumptions, and the provenance module records them as exactly that.
      These entries are read from the module that defines the priors, so a
      re-sourced parameter updates here at the next build.</p>
      {_bibliography(bibliography)}
    </div>
  </section>
</div>

<footer>
  Built {_e(built_at)} from the lab's own retrospectives at
  commit <span class="mono">{_e(build["sha"])}</span>. The console, the
  validation record and this generator live at
  <a href="{REPO_URL}">github.com/elyfmiller/flubnf</a>
  &middot; forecasts target the
  <a href="https://github.com/cdcepi/FluSight-forecast-hub">CDC FluSight hub</a>.
  The data behind this page is the file
  <a class="mono dl" href="site.json" download>site.json</a> beside it.
</footer>
</main>

<script type="application/json" id="flubnf-payload">{data_json}</script>
{page_scripts()}
</body></html>
"""
