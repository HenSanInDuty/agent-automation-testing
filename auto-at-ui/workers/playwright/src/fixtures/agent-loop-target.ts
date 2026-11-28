import { readFileSync } from "node:fs";
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
    if (path === "/login") {
      // ADR-046: a login form as real pages write it (id/name "password", a label that is not a sensitive word).
      response.end(`<!doctype html><meta charset="utf-8"><form action="/submit" method="post">
        <label for="username">Tên đăng nhập</label><input id="username" name="username">
        <label for="password">Mật khẩu</label><input type="password" id="password" name="password">
        <button type="submit">Đăng nhập</button></form>`); return;
    }
    // ADR-048 (capability `agent-frozen-clock-v1`): an autoplay carousel driven by a page timer, as on a real site.
    // `/carousel` starts ticking only when the spec calls `startCarousel(periodMs)`; `/carousel-late` starts itself
    // 4 s (page time) after load, so a new document that kept a running clock would change after the operation settled.
    // `/carousel-frames` adds child frames (srcdoc, about:blank, cross-origin): their clocks run a few ms ahead of the
    // main frame's, which made `pauseAt(main time + 1)` throw "Cannot fast-forward to the past" (ADR-048, round 2).
    // Every tick changes the slide link (name and href), so each tick is a distinct state.
    if (path === "/carousel" || path === "/carousel-late" || path === "/carousel-frames") {
      response.end(`<!doctype html><meta charset="utf-8"><style>body{margin:8px;font:14px sans-serif}
        button,a,input{display:inline-block;margin:4px;padding:3px 6px}</style>
        <div id="carousel"><a id="slide" href="#slide0">Slide 0</a></div>
        <a href="/carousel-late">Sang trang trễ</a>
        <a href="${externalOrigin}/popup" target="_blank">Mở popup</a>
        <button type="button" id="late" onclick="setTimeout(function () { document.getElementById('late-out').textContent = 'xong'; }, 50)">Chạm trễ</button>
        <button type="button" onclick="document.getElementById('out').textContent = 'đã đổi'">Đổi nội dung</button>
        <input aria-label="Ô gõ" name="typed">
        <p>Kết quả: <span id="out">chưa đổi</span> <span id="late-out">chưa</span></p>
        ${path === "/carousel-frames" ? `<iframe title="a" srcdoc="<p>in</p>"></iframe><iframe title="b" src="about:blank"></iframe>
        <iframe title="c" src="${externalOrigin}/popup"></iframe>` : ""}
        <div style="height:3000px"></div>
        <script>
          var ticks = 0;
          window.startCarousel = function (period) {
            setInterval(function () {
              ticks++;
              var slide = document.getElementById('slide');
              slide.textContent = 'Slide ' + ticks; slide.setAttribute('href', '#slide' + ticks);
            }, period);
          };
          ${path === "/carousel-late" ? "setTimeout(function () { window.startCarousel(300); }, 4000);" : ""}
        </script>`); return;
    }
    // ADR-046 page text (capability `page-text-v1`): what the page shows, what it hides, and what must not leave.
    if (path === "/page-text") {
      response.end(`<!doctype html><meta charset="utf-8"><style>body{margin:8px;font:14px sans-serif}
        .sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}</style>
        <h1>Trang thử chữ</h1>
        <div role="alert">Sai tên đăng nhập</div>
        <div role="alert"><h3>Lỗi</h3><p>Hết phiên làm việc</p><button type="button">Đóng</button></div>
        <div role="status">Còn 3 việc</div>
        <p>Đoạn văn ngắn hiển thị.</p>
        <p>Trước <input aria-label="Ô nhập" value="giá-trị-ô-nhập"> sau</p>
        <p style="display:none">Đoạn ẩn display</p><p hidden>Đoạn ẩn hidden</p><p aria-hidden="true">Đoạn ẩn aria</p>
        <div aria-hidden="true"><h2>Tiêu đề trong vùng ẩn</h2></div>
        <p style="visibility:hidden">Đoạn ẩn visibility</p><p style="opacity:0">Đoạn mờ</p>
        <p class="sr">Chữ chỉ cho trình đọc</p><p style="position:absolute;left:-9999px">Chữ ngoài màn hình</p>
        <h2>Tiêu đề hai</h2>
        <p contenteditable="true">Đang gõ dở</p>
        <input type="password" aria-label="Mã bí mật" value="MatKhauBiMat1"><textarea aria-label="Ghi chú">nội dung textarea</textarea>
        <p>Chữ thường <script>document.title="chữ trong script"</script><style>.a{content:"chữ trong style"}</style>và hết</p>
        <p>${"Chữ dài ".repeat(40)}</p>`); return;
    }
    if (path === "/page-text-sensitive") {
      response.end(`<!doctype html><meta charset="utf-8"><h1>Hồ sơ</h1><h2>Reset password</h2>
        <p>Liên hệ nguoi.dung@example.com để lấy lại</p><p>password=abc123 vừa nhập</p><p>token ghi nhớ: abcdef</p>
        <p>Mã đơn 1234567890</p><p>Xem https://example.com/x</p><p>An toàn: còn 5 lượt</p><div role="alert">Sai mật khẩu</div>`);
      return;
    }
    if (path === "/page-text-samples") {
      // Strings shared with the Python contract test; one paragraph each.
      const { samples } = JSON.parse(readFileSync(new URL("../../../../packages/contracts/fixtures/vision-page-text-v1/samples.json", import.meta.url), "utf8")) as
        { samples: Array<{ text: string }> };
      response.end(`<!doctype html><meta charset="utf-8">${samples.map(sample => `<p>${sample.text}</p>`).join("")}`); return;
    }
    if (path === "/page-text-many") {
      response.end(`<!doctype html><meta charset="utf-8"><h1>Danh sách</h1>${
        Array.from({ length: 30 }, (_, i) => `<p>Mục số ${i + 1}</p>`).join("")}`); return;
    }
    if (path === "/page-text-bytes") {
      // 152 characters of 3 bytes each: 9 of these fit the 4096-byte cap, the tenth does not.
      response.end(`<!doctype html><meta charset="utf-8">${
        Array.from({ length: 12 }, (_, i) => `<p>${String(i).padStart(2, "0")}${"ế".repeat(150)}</p>`).join("")}`); return;
    }
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
