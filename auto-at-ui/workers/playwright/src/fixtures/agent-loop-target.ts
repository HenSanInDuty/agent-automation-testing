import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

// Synthetic, loopback-only target for the agent mode specs: two origins, no external network.
// `origin` hosts the controls; `externalOrigin` is a second loopback port (a different origin).
const PIXEL = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");

const listen = (server: Server) => new Promise<string>((resolve) => server.listen(0, "127.0.0.1", () =>
  resolve(`http://127.0.0.1:${(server.address() as AddressInfo).port}`)));
const stop = async (server: Server) => {
  server.closeAllConnections();
  await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
};

function index(externalOrigin: string): string {
  const decomposed = "XOÁ".normalize("NFD");
  return `<!doctype html><meta charset="utf-8"><style>body{margin:8px;font:14px sans-serif}
    button,a,input{display:inline-block;margin:4px;padding:3px 6px}</style>
    <form id="profile" action="/submit" method="post">
      <input aria-label="Ô một" name="one"><input aria-label="Ô hai" name="two"><input aria-label="Ô ba" name="three">
      <button type="submit">Gửi đi</button><button>Tiếp tục</button>
    </form>
    <div>
      <a href="${externalOrigin}/popup" target="_blank">Liên kết ngoài</a>
      <a href="/file.bin" download>Tải về</a>
      <a href="/attachment.bin">Tệp đính kèm</a>
      <a href="/next">Trang kế</a>
      <a href="/beforeunload">Trang beforeunload</a>
      <a href="${externalOrigin}/popup" target="_blank">ĐĂNG KÝ</a>
    </div>
    <div>
      <button type="button" onclick="confirm('Chắc chứ?')">Hỏi xác nhận</button>
      <button type="button" onclick="alert('Báo động')">Báo động</button>
      <button type="button" onclick="prompt('Nhập gì đó')">Nhập liệu</button>
      <button type="button" onclick="document.getElementById('out').textContent='đã đổi'">Đổi nội dung</button>
      <button type="button" onclick="this.dataset.clicked='yes'">NẠP THẺ</button>
      <button type="button" onclick="this.dataset.clicked='yes'">Xoá tài khoản</button>
      <button type="button" onclick="this.dataset.clicked='yes'">${decomposed}</button>
    </div>
    <p>Kết quả: <span id="out">chưa đổi</span></p>
    <img alt="" src="${externalOrigin}/pixel.png" width="1" height="1">`;
}

export async function startAgentLoopTarget() {
  // Per-origin request log ("METHOD /path"), read by specs to prove what did or did not reach the server.
  const requests: string[] = [], externalRequests: string[] = [];
  const external = createServer((request, response) => {
    externalRequests.push(`${request.method} ${request.url}`);
    if (request.url === "/pixel.png") {
      response.setHeader("content-type", "image/png"); response.end(PIXEL); return;
    }
    response.setHeader("content-type", "text/html; charset=utf-8");
    response.end(`<!doctype html><meta charset="utf-8"><button type="button" onclick="this.dataset.clicked='yes'">Bấm trong popup</button>`);
  });
  const externalOrigin = await listen(external);
  const main = createServer((request, response) => {
    const path = request.url ?? "/";
    requests.push(`${request.method} ${path}`);
    response.setHeader("cache-control", "no-store");
    if (path === "/file.bin" || path === "/attachment.bin") {
      response.setHeader("content-type", "application/octet-stream");
      response.setHeader("content-disposition", "attachment; filename=fixture.bin");
      response.end("fixture"); return;
    }
    response.setHeader("content-type", "text/html; charset=utf-8");
    if (path === "/next") { response.end(`<!doctype html><meta charset="utf-8"><a href="/">Về trang chủ</a>`); return; }
    if (path === "/submit") { response.end(`<!doctype html><meta charset="utf-8"><p>Đã gửi</p>`); return; }
    if (path === "/beforeunload") {
      response.end(`<!doctype html><meta charset="utf-8"><a href="/next">Rời trang</a>
        <script>addEventListener('beforeunload', event => { event.preventDefault(); event.returnValue = ''; });</script>`);
      return;
    }
    response.end(index(externalOrigin));
  });
  const origin = await listen(main);
  return { origin, externalOrigin, requests, externalRequests,
    close: async () => { await stop(main); await stop(external); } };
}
