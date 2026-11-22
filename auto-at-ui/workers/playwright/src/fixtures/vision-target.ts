import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { visualButtonsDatasetPage } from "./visual-buttons-dataset.js";

// Synthetic, loopback-only target; no provider, credentials or production data.
export async function startVisionTarget() {
  const visits = new Map<string, number>();
  const server = createServer((request, response) => {
    const path = request.url ?? "/";
    visits.set(path, (visits.get(path) ?? 0) + 1);
    response.setHeader("content-type", "text/html; charset=utf-8");
    response.setHeader("cache-control", "no-store");
    if (path === "/visual-buttons-dataset") {
      response.end(visualButtonsDatasetPage());
      return;
    }
    if (path.startsWith("/record-button/")) { response.end("recorded"); return; }
    if (path === "/close-race-child") {
      response.end(`<!doctype html><button id="content">Initial</button><script>
        let applied=0;setInterval(async()=>{
          const n=Number(await(await fetch('/close-race-status')).text());
          if(n===applied)return;document.querySelector('#content').textContent='Hydrated '+n;
          applied=n;await fetch('/close-race-applied/'+n);
        },30);
      </script>`); return;
    }
    if (path === "/close-race-status") {
      response.end(String(visits.get('/close-race-release') ?? 0)); return;
    }
    if (path.startsWith('/close-race-')) { response.end('ok'); return; }
    if (path === "/restore-race" || path === "/close-race") {
      response.end(`<!doctype html><input type="hidden" value="fixture-original">
        <a href="${path === '/close-race' ? '/close-race-child' : '/a'}" target="_blank" style="display:inline-block;padding:15px;background:gold;border-radius:6px"
          onclick="fetch('/record-button/popup')">Popup</a>
        <button id="sibling" style="margin-left:40px" onclick="fetch('/record-button/sibling')">Sibling</button>
        <script>
        let applied='stable';setInterval(async()=>{
          const next=await(await fetch('/restore-race-status')).text();
          if(next===applied)return;
          if(next==='form')document.querySelector('input').value='fixture-changed';
          else document.querySelector('#sibling').textContent=next==='changed'?'Changed':'Sibling';
          applied=next;await fetch('/restore-race-applied/'+next);
        },30);
        </script>`); return;
    }
    if (path === "/restore-race-status") {
      response.end(visits.has('/restore-race-reset') ? 'stable' :
        visits.has('/restore-race-form') ? 'form' :
        visits.has('/restore-race-release') ? 'changed' : 'stable'); return;
    }
    if (path.startsWith('/restore-race-')) { response.end('ok'); return; }
    if (path === "/codex-two-branches") {
      response.end('<!doctype html><a href="/a">Branch A</a><a href="/b" style="margin-left:40px">Branch B</a>');
      return;
    }
    if (path === "/visual-buttons-navigation" || path === "/visual-buttons-navigation-drift") {
      response.end(`<!doctype html><style>body{margin:0;height:1400px}a{position:absolute;left:20px;width:150px;height:40px;border-radius:5px;background:gold}</style>
        <a style="top:20px" target="_blank" href="${path.endsWith('-drift') ? '/late-popup' : '/a'}">Popup</a>
        <a style="top:100px" href="/a">Open</a><a style="top:180px" href="/b">Open</a>
        <div style="position:absolute;top:1000px;left:20px;width:100px;height:40px;background:linear-gradient(red,blue);cursor:pointer" onclick="void 0">Custom</div>`);
      return;
    }
    if (path === "/late-popup") {
      response.end(`<!doctype html><h1>Popup</h1><script>
        const timer=setInterval(async()=>{
          if(await (await fetch('/popup-release-status')).text()!=='ready')return;
          clearInterval(timer);
          document.body.innerHTML='<h1>Hydrated popup</h1><input value="fixture-private">';
          await fetch('/popup-hydrated');
        },50);
        </script>`);
      return;
    }
    if (path === "/popup-release-status") {
      response.end(visits.has('/popup-release') ? 'ready' : 'waiting');
      return;
    }
    if (path === "/popup-release" || path === "/popup-hydrated") { response.end('ok'); return; }
    if (path === "/coverage-popup") {
      response.end('<!doctype html><a href="/coverage-popup-child" target="_blank">Popup</a><a href="/a" style="margin-left:40px">Sibling</a>');
      return;
    }
    if (path === "/coverage-popup-child") {
      response.end('<!doctype html><input type="hidden" value="seed"><a href="/b">Child content</a>');
      return;
    }
    if (path === "/coverage-scroll") {
      response.end('<!doctype html><style>body{margin:0;height:1250px}a{position:absolute;left:30px;padding:15px}</style><a href="/a" style="top:20px">Header</a><a href="/b" style="top:950px">Lower content</a>');
      return;
    }
    if (path === "/scan-carousel") {
      response.end(`<!doctype html><style>body{margin:0;height:1100px}button{position:absolute;left:30px;padding:15px}</style>
        <h1>Viewport fixture</h1><button style="top:90px">Unrelated header</button>
        <button style="top:850px" onclick="fetch('/record-button/lower')">Lower action</button>
        <div id="carousel" style="cursor:pointer;position:absolute;left:400px;top:150px;width:100px;height:50px">Slide</div>
        <input type="hidden" value="fixture-private-value">
        <script>let n=0;setInterval(()=>document.querySelector('#carousel').style.left=(400+30*(++n%4))+'px',3000)</script>`);
      return;
    }
    if (path === "/coverage-buttons") {
      response.end(`<!doctype html><style>body{margin:0;height:1250px}a,button{position:absolute;left:30px;padding:15px}</style>
        <a href="/a" style="top:20px">Article</a><button style="top:950px">Lower button</button>
        <script>let n=0;setInterval(()=>document.querySelector('a').style.transform='translateX('+(++n%40)+'px)',20)</script>`);
      return;
    }
    if (path === "/coverage-button-tabs") {
      response.end(`<!doctype html><style>body{margin:0;height:1250px}button{position:absolute;left:30px;padding:15px}</style>
        <button style="top:20px" onclick="document.querySelector('#lower').textContent='Lower Alpha';document.querySelector('#lower').hidden=false">Alpha</button>
        <button style="top:80px" onclick="document.querySelector('#lower').textContent='Lower Beta';document.querySelector('#lower').hidden=false">Beta</button>
        <button id="lower" hidden style="top:950px">Lower initial</button>`);
      return;
    }
    if (path === "/coverage-mutation-cross-viewport") {
      response.end(`<!doctype html><style>body{margin:0;height:1100px}button{position:absolute;left:30px;padding:15px}</style>
        <input type="hidden" value="fixture-original">
        <button hidden style="top:20px" aria-pressed="false" onclick="fetch('/record-button/mutate');this.setAttribute('aria-pressed','true');document.querySelector('#sibling').setAttribute('aria-pressed','true')">Mutate</button>
        <button style="top:800px" onclick="fetch('/record-button/reveal');document.querySelectorAll('[hidden]').forEach(el=>el.hidden=false)">Reveal</button>
        <button hidden style="top:880px" onclick="fetch('/record-button/top');window.scrollTo(0,0)">Top</button>
        <button id="sibling" hidden style="top:960px" aria-pressed="false" onclick="fetch('/record-button/sibling')">Sibling</button>`);
      return;
    }
    if (path === "/coverage-popup-scroll" || path === "/coverage-popup-scroll-form") {
      response.end(`<!doctype html><style>body{margin:0;height:1100px}button{position:absolute;left:30px;padding:15px}</style>
        <input type="hidden" value="fixture-original">
        <button id="popup" hidden style="top:20px" onclick="${path.endsWith('-form') ? "document.querySelector('input').value='fixture-changed';" : ''}fetch('/record-button/popup');window.open('/a','_blank')">Popup</button>
        <button style="top:800px" onclick="fetch('/record-button/reveal');document.querySelectorAll('[hidden]').forEach(el=>el.hidden=false)">Reveal</button>
        <button hidden style="top:880px" onclick="fetch('/record-button/top');window.scrollTo(0,0)">Top</button>
        <button hidden style="top:960px" onclick="fetch('/record-button/sibling')">Sibling</button>`);
      return;
    }
    if (path === "/coverage-visual-noop-batch" || path === "/coverage-visual-noop-replacement") {
      response.end(`<!doctype html><style>button{position:absolute;width:120px;height:40px}</style>${
        Array.from({ length: 12 }, (_, i) => `<button style="left:${20 + (i % 3) * 160}px;top:${20 + Math.floor(i / 3) * 80}px"
          onclick="fetch('/record-button/noop-${i}');${path.endsWith('-replacement') && i === 0
            ? "const next=document.querySelectorAll('button')[1];next.replaceWith(next.cloneNode(true));" : ''}">Button ${i}</button>`).join('')}`);
      return;
    }
    if (path === "/coverage-mutation-queue" || path === "/coverage-mutation-queue-form") {
      response.end(`<!doctype html><body>${path.endsWith('-form') ? '<input type="hidden" value="fixed-private-fixture">' : ''}
        <button aria-pressed="false" onclick="fetch('/record-button/tab-a');this.setAttribute('aria-pressed','true')">Tab A</button>
        <button aria-pressed="false" onclick="fetch('/record-button/tab-b');this.setAttribute('aria-pressed','true')">Tab B</button></body>`);
      return;
    }
    if (path === "/coverage-panel-order") {
      response.end(`<!doctype html><style>button,a{display:inline-block;padding:12px;margin:8px;background:gold;border-radius:6px}</style>
        <input type="hidden" value="fixed-private-fixture">
        <div><button onclick="fetch('/record-button/current-tab')">Current tab</button>
        <button onclick="fetch('/record-button/other-tab');document.querySelector('#panel').remove();this.setAttribute('aria-pressed','true')">Other tab</button></div>
        <section id="panel"><div><button onclick="fetch('/record-button/child-one')">Child one</button>
        <button onclick="fetch('/record-button/child-two')">Child two</button></div></section>
        <a href="/a">Destination</a>`);
      return;
    }
    if (path === "/coverage-deep-tabs") {
      response.end(`<!doctype html><body>${Array.from({ length: 12 }, (_, i) =>
        `<button ${i ? 'hidden' : ''} onclick="fetch('/record-button/deep-${i}');this.hidden=true;${
          i < 11 ? `document.querySelectorAll('button')[${i + 1}].hidden=false;` : ''}">Tab ${i}</button>`).join('')}</body>`);
      return;
    }
    if (path === "/coverage-compact-scan") {
      response.end(`<!doctype html><body style="margin:0;height:2900px">${
        Array.from({ length: 45 }, (_, i) => `<button style="position:absolute;left:${20 + i % 3 * 180}px;top:${20 + Math.floor(i / 3) * 190}px;width:140px;height:42px"
          onclick="fetch('/record-button/compact-${i}')">Action ${i}</button>`).join('')}
        </body>`); return;
    }
    if (path === "/coverage-visual-empty") { response.end('<!doctype html><body></body>'); return; }
    if (path === "/coverage-visual-delayed") {
      response.end(`<!doctype html><body><script>
        const timer=setInterval(async()=>{
          if(await (await fetch('/initial-release-status')).text()!=='ready')return;
          clearInterval(timer);
          const button=document.createElement('button');button.textContent='Late button';
          button.onclick=()=>fetch('/record-button/late');document.body.replaceChildren(button);
          await fetch('/initial-hydrated');
        },50);
        </script></body>`);
      return;
    }
    if (path === '/coverage-video-preflight') {
      response.end(`<!doctype html><style>a{display:inline-block;width:140px;height:60px;background:#234;border-radius:8px;color:white}</style>
        <a href="/a" target="_blank">Video</a><a href="/b" target="_blank">Video</a><input type="hidden" value="fixture-private-original">`);
      return;
    }
    if (path === "/initial-release-status") {
      response.end(visits.has('/initial-release') ? 'ready' : 'waiting'); return;
    }
    if (path === "/initial-release" || path === "/initial-hydrated") { response.end('ok'); return; }
    if (["/coverage-history-delay", "/coverage-history-duplicate",
      "/coverage-history-duplicate-form", "/coverage-history-overwritten",
      "/coverage-history-overwritten-unreachable",
      "/coverage-history-scroll-reset", "/coverage-history-scroll-reset-form",
      "/coverage-history-scroll-reset-up"].includes(path)) {
      // `-unreachable` (ADR-044): the Reveal cluster sits below the fold and a root-level
      // "Top action" stays reachable by URL after the revealed branch can no longer be restored.
      response.end(`<!doctype html><style>button,a{display:inline-block;margin:20px;padding:15px;background:gold;border-radius:5px}</style><body><script>
        const home=location.pathname;let revealed=false,returned=false;
        const resetScroll=${path.startsWith('/coverage-history-scroll-reset')};
        const resetUp=${path.endsWith('-reset-up')};
        if(resetScroll)history.scrollRestoration='manual';
        const unreachable=${path.endsWith('-unreachable')};
        function root(){
          if(resetScroll)document.body.style.cssText='margin:0;padding-top:'+(resetUp?0:800)+'px;height:1100px;box-sizing:border-box';
          if(unreachable)document.body.style.cssText='margin:0;padding-top:900px;height:1300px;box-sizing:border-box';
          document.body.innerHTML=(unreachable?'<button id="top-action" style="position:absolute;top:20px;left:20px">Top action</button>':'')+'<input type="hidden" value="fixture-original"><button id="reveal">Reveal</button><span id="actions" hidden><a href="/history-destination" id="next">Next</a><button id="sibling">Sibling</button></span>';
          if(unreachable)document.querySelector('#top-action').onclick=()=>fetch('/record-button/top-action');
          document.querySelector('#actions').hidden=!revealed;
          if(returned && ${path.endsWith('-form')})document.querySelector('input').value='fixture-changed';
          if(returned && resetScroll)window.scrollTo(0,resetUp?300:0);
          document.querySelector('#reveal').onclick=()=>{fetch('/record-button/reveal');revealed=true;document.querySelector('#actions').hidden=false};
          document.querySelector('#sibling').onclick=()=>fetch('/record-button/sibling');
          document.querySelector('#next').onclick=event=>{event.preventDefault();fetch('/record-button/next');
            if(${path.includes('-overwritten')})history.replaceState({},'', '/overwritten-source');
            history.pushState({},'', '/history-destination');
            if(${path !== '/coverage-history-delay'})history.pushState({},'', '/history-destination?view=latest');
            document.body.innerHTML='<h1>Destination</h1><input type="hidden" value="fixture-original">'};
        }
        window.addEventListener('popstate',()=>{
          if(${path !== '/coverage-history-delay'}){
            if(location.pathname===home){returned=true;root();}return;
          }
          const timer=setInterval(async()=>{
            if(await (await fetch('/history-release-status')).text()!=='ready')return;
            clearInterval(timer);root();await fetch('/history-hydrated');
          },50);
        });root();
        </script></body>`);
      return;
    }
    if (path === "/history-release-status") {
      response.end(visits.has('/history-release') ? 'ready' : 'waiting'); return;
    }
    if (path === "/history-release" || path === "/history-hydrated") { response.end('ok'); return; }
    if (path === "/coverage-anonymous-buttons") {
      response.end(`<!doctype html><style>body{margin:0;height:1250px}button{position:absolute;left:30px;width:50px;height:30px}</style>
        <button style="top:20px"></button><button style="top:950px"></button>`);
      return;
    }
    if (path === "/page-inventory") {
      response.end('<!doctype html><style>a{display:inline-block;margin:30px;padding:10px;transform:scale(1.1)}</style><a href="/page-inventory">Home</a><a href="/a">News</a><a href="/b">Events</a>');
      return;
    }
    if (path === "/a" || path === "/b") { response.end(`<h1>Branch ${path.slice(1).toUpperCase()}</h1>`); return; }
    if (path === "/frame") { response.end('<button aria-label="Embedded action" style="margin:20px">Frame</button>'); return; }
    if (path === "/download-redirect") {
      response.writeHead(302, { location: '/download?private_fixture=do-not-export' }); response.end(); return;
    }
    if (path === "/download" || path.startsWith("/download?")) { response.setHeader("content-disposition", 'attachment; filename="fixture.txt"'); response.end("fixture"); return; }
    response.end(`<!doctype html><html><head><style>
      body{margin:0;min-height:2200px;font:16px sans-serif} .action{position:absolute;left:20px;width:180px;height:40px}
      a.action{display:block;box-sizing:border-box;padding:10px;background:#ddd} button{font:16px sans-serif}
    </style></head><body>
      <a class="action" style="top:20px" href="/a">Branch A</a>
      <a class="action" style="top:80px" href="/b">Branch B</a>
      <button class="action" style="top:140px" onclick="document.getElementById('modal').hidden=!document.getElementById('modal').hidden">Toggle modal</button>
      <section id="modal" hidden style="position:absolute;top:500px;left:20px">Modal content</section>
      <a class="action" style="top:200px" href="/a" target="_blank">Open popup</a>
      <input class="action" style="top:260px" aria-label="Search" value="seed">
      <button class="action" style="top:320px" onclick="this.dataset.count=String(Number(this.dataset.count||0)+1)"><svg width="20" height="20"><circle cx="10" cy="10" r="8" /></svg><span>Icon action</span></button>
      <button class="action" style="top:380px">No operation</button>
      <a class="action" style="top:440px" href="http://localhost:1/denied" target="_blank">Denied popup</a>
      <button style="position:absolute;left:300px;top:20px">Duplicate</button>
      <button style="position:absolute;left:450px;top:20px">Duplicate</button>
      <section id="shadow-host" style="position:absolute;left:300px;top:80px"></section>
      <iframe id="embedded" src="/frame" style="position:absolute;left:300px;top:160px;width:350px;height:100px"></iframe>
      <button style="position:absolute;left:300px;top:300px" aria-label="user@example.test">Sensitive</button>
      <button id="hydrate" style="position:absolute;left:300px;top:360px">Hydrate</button>
      <button style="position:absolute;left:300px;top:420px" onclick="alert('fixture')">Dialog</button>
      <a style="position:absolute;left:300px;top:470px" href="/download" download>Download fixture</a>
      <div role="button" tabindex="0" class="action" style="top:560px" aria-pressed="false" onclick="this.dataset.clicked='yes';this.setAttribute('aria-pressed','true')">Custom div action</div>
      <span role="button" tabindex="0" class="action" style="top:620px" onclick="this.dataset.clicked='yes'">Custom span action</span>
      <button class="action" style="top:1500px" onclick="this.dataset.clicked='yes'">Offscreen action</button>
      ${path === "/?animated=1" ? `<section id="carousel" style="position:absolute;top:1800px">Slide</section>
      <script>
        let slide = 0;
        setInterval(() => {
          const carousel = document.getElementById('carousel');
          carousel.className = 'slide-' + (++slide % 3);
          carousel.textContent = 'Slide ' + slide;
        }, 50);
      </script>` : ""}
      <script>document.getElementById('shadow-host').attachShadow({mode:'open'}).innerHTML='<button aria-label="Shadow action">Shadow</button>';</script>
    </body></html>`);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return { origin: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, visits,
    close: async () => { server.closeAllConnections(); await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())); } };
}
