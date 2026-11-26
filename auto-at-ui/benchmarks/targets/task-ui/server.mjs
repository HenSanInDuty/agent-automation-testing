// Deterministic local web UI used to test the agent_loop task-testing engine (ADR-046).
// No timers, animations, randomness or external requests. State lives in this process only;
// POST /__reset restores the initial state.
//
// INTENTIONAL DEFECTS: /broken is defective on purpose so negative tasks have a ground truth.
//   1. "Lưu thay đổi" does nothing: no message, no navigation, no state change.
//   2. "Đếm" never changes the displayed number (it stays at 0).
// Do not "fix" them; tasks.v1.json expects `not_achieved` for those pages.
import { createServer } from "node:http";

const PORT = Number(process.env.PORT ?? 7300);
const ACCOUNT = { username: "demo", password: "Demo1234" };

const initialTodos = () => [
  { id: 1, text: "Học bài", done: false },
  { id: 2, text: "Đi chợ", done: true },
];
const state = { todos: initialTodos(), nextId: 3, sessions: new Map(), nextSession: 1 };

const reset = () => {
  state.todos = initialTodos();
  state.nextId = 3;
  state.sessions = new Map();
  state.nextSession = 1;
};

const PRODUCTS = [
  { name: "Áo thun cotton", price: "150.000 đ" },
  { name: "Áo khoác gió", price: "420.000 đ" },
  { name: "Quần jean nam", price: "380.000 đ" },
  { name: "Giày thể thao", price: "650.000 đ" },
  { name: "Balo laptop", price: "310.000 đ" },
  { name: "Tai nghe không dây", price: "890.000 đ" },
  { name: "Bình giữ nhiệt", price: "210.000 đ" },
  { name: "Đèn bàn LED", price: "180.000 đ" },
];

const esc = (value) => String(value).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fold = (value) => String(value).normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();

const NAV = [
  ["/", "Trang chủ"],
  ["/login", "Đăng nhập"],
  ["/todos", "Việc cần làm"],
  ["/tabs", "Thẻ thông tin"],
  ["/search", "Tìm kiếm"],
  ["/broken", "Trang thử lỗi"],
];

const layout = (title, path, body, script = "") => `<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)} - Task UI</title>
<style>
body { font-family: Arial, sans-serif; margin: 0; color: #1a1a1a; }
nav { background: #20324a; padding: 12px 24px; }
nav ul { list-style: none; margin: 0; padding: 0; display: flex; gap: 20px; }
nav a { color: #fff; }
nav a[aria-current="page"] { font-weight: bold; text-decoration: underline; }
main { padding: 24px; max-width: 760px; }
label { display: block; margin: 12px 0 4px; }
input[type="text"], input[type="password"] { padding: 6px; width: 260px; }
button { padding: 6px 14px; margin-top: 8px; }
.error { color: #b00020; }
.overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5); display: flex; align-items: center; justify-content: center; }
.overlay[hidden] { display: none; }
.dialog { background: #fff; padding: 24px; max-width: 420px; }
[role="tablist"] { display: flex; gap: 4px; }
[role="tab"][aria-selected="true"] { font-weight: bold; border-bottom: 3px solid #20324a; }
[role="tabpanel"][hidden] { display: none; }
</style>
</head>
<body>
<nav aria-label="Điều hướng chính"><ul>
${NAV.map(([href, label]) =>
  `<li><a href="${href}"${href === path ? ' aria-current="page"' : ""}>${esc(label)}</a></li>`).join("\n")}
</ul></nav>
<main>
${body}
</main>
${script ? `<script>\n${script}\n</script>` : ""}
</body>
</html>`;

const homePage = () => layout("Trang chủ", "/", `
<h1>Chào mừng đến với Task UI</h1>
<p>Đây là trang thử nghiệm dùng để kiểm tra các tác vụ giao diện.</p>
<button type="button" id="open-intro" aria-haspopup="dialog">Mở hộp thoại giới thiệu</button>
<div class="overlay" id="intro-overlay" hidden>
  <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="intro-title" aria-describedby="intro-text">
    <h2 id="intro-title">Giới thiệu</h2>
    <p id="intro-text">Đây là hộp thoại giới thiệu của trang thử nghiệm.</p>
    <button type="button" id="close-intro">Đóng hộp thoại</button>
  </div>
</div>`, `
const overlay = document.getElementById("intro-overlay");
const opener = document.getElementById("open-intro");
const closer = document.getElementById("close-intro");
function closeDialog() { overlay.hidden = true; opener.focus(); }
opener.addEventListener("click", () => { overlay.hidden = false; closer.focus(); });
closer.addEventListener("click", closeDialog);
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !overlay.hidden) closeDialog(); });`);

const loginPage = (error = "", username = "") => layout("Đăng nhập", "/login", `
<h1>Đăng nhập</h1>
<form method="post" action="/login" novalidate>
  ${error ? `<p class="error" role="alert">${esc(error)}</p>` : ""}
  <label for="username">Tên đăng nhập</label>
  <input type="text" id="username" name="username" autocomplete="off" value="${esc(username)}">
  <label for="password">Mật khẩu</label>
  <input type="password" id="password" name="password" autocomplete="off">
  <button type="submit">Đăng nhập</button>
</form>`);

const dashboardPage = (user) => layout("Bảng điều khiển", "/dashboard", `
<h1>Bảng điều khiển</h1>
<p role="status">Xin chào, ${esc(user)}</p>
<form method="post" action="/logout"><button type="submit">Đăng xuất</button></form>`);

const todosPage = () => {
  const done = state.todos.filter((todo) => todo.done).length;
  const items = state.todos.map((todo) => `
  <li>
    <form method="post" action="/todos/toggle">
      <input type="hidden" name="id" value="${todo.id}">
      <input type="checkbox" id="done-${todo.id}" ${todo.done ? "checked" : ""} onchange="this.form.submit()">
      <label for="done-${todo.id}" style="display:inline">hoàn thành: ${esc(todo.text)}</label>
      <noscript><button type="submit">Cập nhật</button></noscript>
    </form>
    <form method="post" action="/todos/delete">
      <input type="hidden" name="id" value="${todo.id}">
      <button type="submit" aria-label="Xoá ${esc(todo.text)}">Xoá</button>
    </form>
  </li>`).join("");
  return layout("Việc cần làm", "/todos", `
<h1>Việc cần làm</h1>
<form method="post" action="/todos/add">
  <label for="new-todo">Việc mới</label>
  <input type="text" id="new-todo" name="text" autocomplete="off">
  <button type="submit">Thêm</button>
</form>
<p id="counter" role="status">${state.todos.length} việc, ${done} đã xong</p>
<ul aria-label="Danh sách việc">${items}
</ul>`);
};

const tabsPage = () => layout("Thẻ thông tin", "/tabs", `
<h1>Thẻ thông tin</h1>
<div role="tablist" aria-label="Thông tin sản phẩm">
  <button type="button" role="tab" id="tab-overview" aria-controls="panel-overview" aria-selected="true">Tổng quan</button>
  <button type="button" role="tab" id="tab-details" aria-controls="panel-details" aria-selected="false" tabindex="-1">Chi tiết</button>
  <button type="button" role="tab" id="tab-settings" aria-controls="panel-settings" aria-selected="false" tabindex="-1">Cài đặt</button>
</div>
<div role="tabpanel" id="panel-overview" aria-labelledby="tab-overview"><p>Nội dung tổng quan: sản phẩm được bảo hành 12 tháng.</p></div>
<div role="tabpanel" id="panel-details" aria-labelledby="tab-details" hidden><p>Nội dung chi tiết: trọng lượng 450 gam, màu xanh.</p></div>
<div role="tabpanel" id="panel-settings" aria-labelledby="tab-settings" hidden><p>Nội dung cài đặt: chế độ tiết kiệm điện đang tắt.</p></div>`, `
const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
function select(tab) {
  for (const other of tabs) {
    const active = other === tab;
    other.setAttribute("aria-selected", String(active));
    other.tabIndex = active ? 0 : -1;
    document.getElementById(other.getAttribute("aria-controls")).hidden = !active;
  }
}
for (const tab of tabs) tab.addEventListener("click", () => select(tab));`);

const searchPage = (query) => {
  const matches = PRODUCTS.filter((product) => fold(product.name).includes(fold(query.trim())));
  const rows = PRODUCTS.map((product) => {
    const shown = matches.includes(product);
    return shown ? `<li data-name="${esc(fold(product.name))}">${esc(product.name)} - ${esc(product.price)}</li>` : "";
  }).join("\n");
  return layout("Tìm kiếm", "/search", `
<h1>Tìm kiếm sản phẩm</h1>
<form method="get" action="/search" role="search">
  <label for="q">Từ khoá</label>
  <input type="text" id="q" name="q" autocomplete="off" value="${esc(query)}">
  <button type="submit">Tìm</button>
</form>
<p id="empty" role="status"${matches.length ? " hidden" : ""}>Không tìm thấy sản phẩm</p>
<ul id="results" aria-label="Kết quả tìm kiếm">
${rows}
</ul>`, `
const input = document.getElementById("q");
const items = Array.from(document.querySelectorAll("#results li"));
const empty = document.getElementById("empty");
const fold = (v) => v.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
input.addEventListener("input", () => {
  const needle = fold(input.value.trim());
  let visible = 0;
  for (const item of items) {
    const match = item.dataset.name.includes(needle);
    item.hidden = !match;
    if (match) visible += 1;
  }
  empty.hidden = visible > 0;
});`);
};

// Defective on purpose; see the header comment.
const brokenPage = () => layout("Trang thử lỗi", "/broken", `
<h1>Trang thử lỗi</h1>
<form onsubmit="return false">
  <label for="note">Ghi chú</label>
  <input type="text" id="note" name="note" autocomplete="off">
  <button type="button" id="save">Lưu thay đổi</button>
</form>
<p>Số lần đếm: <output id="count">0</output></p>
<button type="button" id="counter-button">Đếm</button>`, `
// Intentionally empty handlers: no feedback, no state change.
document.getElementById("save").addEventListener("click", () => {});
document.getElementById("counter-button").addEventListener("click", () => {});`);

const notFoundPage = () => layout("Không tìm thấy", "", `<h1>Không tìm thấy trang</h1>`);

const readForm = (request) => new Promise((resolve) => {
  let raw = "";
  request.on("data", (chunk) => { if (raw.length < 10_000) raw += chunk; });
  request.on("end", () => resolve(new URLSearchParams(raw)));
});

const sessionUser = (request) => {
  const match = /(?:^|;\s*)sid=([\w-]+)/.exec(request.headers.cookie ?? "");
  return match ? state.sessions.get(match[1]) ?? null : null;
};

const html = (response, body, status = 200, headers = {}) => {
  response.writeHead(status, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", ...headers });
  response.end(body);
};
const redirect = (response, location, headers = {}) => {
  response.writeHead(303, { location, "cache-control": "no-store", ...headers });
  response.end();
};

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");
  const route = `${request.method} ${url.pathname}`;
  switch (route) {
    case "GET /healthz":
      return html(response, "ok");
    case "POST /__reset":
      reset();
      response.writeHead(200, { "content-type": "application/json" });
      return response.end(JSON.stringify({ reset: true }));
    case "GET /":
      return html(response, homePage());
    case "GET /login":
      return html(response, loginPage());
    case "POST /login": {
      const form = await readForm(request);
      const username = (form.get("username") ?? "").trim();
      const password = form.get("password") ?? "";
      if (!username || !password) {
        return html(response, loginPage("Vui lòng nhập tên đăng nhập và mật khẩu", username));
      }
      if (username !== ACCOUNT.username || password !== ACCOUNT.password) {
        return html(response, loginPage("Sai tên đăng nhập hoặc mật khẩu", username));
      }
      const sid = `session-${state.nextSession++}`;
      state.sessions.set(sid, username);
      return redirect(response, "/dashboard", { "set-cookie": `sid=${sid}; Path=/; HttpOnly; SameSite=Lax` });
    }
    case "GET /dashboard": {
      const user = sessionUser(request);
      return user ? html(response, dashboardPage(user)) : redirect(response, "/login");
    }
    case "POST /logout": {
      const match = /(?:^|;\s*)sid=([\w-]+)/.exec(request.headers.cookie ?? "");
      if (match) state.sessions.delete(match[1]);
      return redirect(response, "/login", { "set-cookie": "sid=; Path=/; Max-Age=0" });
    }
    case "GET /todos":
      return html(response, todosPage());
    case "POST /todos/add": {
      const text = ((await readForm(request)).get("text") ?? "").trim().slice(0, 100);
      if (text) state.todos.push({ id: state.nextId++, text, done: false });
      return redirect(response, "/todos");
    }
    case "POST /todos/toggle": {
      const id = Number((await readForm(request)).get("id"));
      const todo = state.todos.find((item) => item.id === id);
      if (todo) todo.done = !todo.done;
      return redirect(response, "/todos");
    }
    case "POST /todos/delete": {
      const id = Number((await readForm(request)).get("id"));
      state.todos = state.todos.filter((item) => item.id !== id);
      return redirect(response, "/todos");
    }
    case "GET /tabs":
      return html(response, tabsPage());
    case "GET /search":
      return html(response, searchPage(url.searchParams.get("q") ?? ""));
    case "GET /broken":
      return html(response, brokenPage());
    default:
      return html(response, notFoundPage(), 404);
  }
});

server.listen(PORT, "0.0.0.0");
