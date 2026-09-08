import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

// Synthetic, loopback-only target; no provider, credentials or production data.
export async function startVisionTarget() {
  const visits = new Map<string, number>();
  const server = createServer((request, response) => {
    const path = request.url ?? "/";
    visits.set(path, (visits.get(path) ?? 0) + 1);
    response.setHeader("content-type", "text/html; charset=utf-8");
    response.setHeader("cache-control", "no-store");
    if (path === "/a" || path === "/b") { response.end(`<h1>Branch ${path.slice(1).toUpperCase()}</h1>`); return; }
    if (path === "/frame") { response.end('<button aria-label="Embedded action" style="margin:20px">Frame</button>'); return; }
    if (path === "/download") { response.setHeader("content-disposition", 'attachment; filename="fixture.txt"'); response.end("fixture"); return; }
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
      <script>document.getElementById('shadow-host').attachShadow({mode:'open'}).innerHTML='<button aria-label="Shadow action">Shadow</button>';</script>
    </body></html>`);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return { origin: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, visits,
    close: async () => { server.closeAllConnections(); await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())); } };
}
