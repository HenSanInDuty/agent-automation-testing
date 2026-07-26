import { createServer } from "node:http";

const pages = {
  "/locator": '<button id="submit-order">Sign in</button>',
  "/dom": '<form><div><button id="submit-order">Sign in</button></div></form>',
  "/text": '<main>Unable to complete sign in</main>',
  "/timing": '<main id="delayed">Loading</main>',
  "/product": '<main>Credentials rejected</main>',
  "/environment": '<main>Identity service unavailable</main>',
  "/flaky": '<main>Seeded race outcome: not-ready</main>',
};

createServer((request, response) => {
  const body = pages[new URL(request.url ?? "/", "http://localhost").pathname] ?? "<main>ok</main>";
  response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  response.end(`<!doctype html><html><body>${body}</body></html>`);
}).listen(7200, "0.0.0.0");
