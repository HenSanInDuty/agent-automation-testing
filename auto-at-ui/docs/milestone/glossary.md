# Auto-AT glossary

This is our shared vocabulary. When a new technical term appears, add it here
with a plain-language definition and an Auto-AT example. Once a term is marked
as understood in a learning session, it will be used without repeating its full
definition unless requested.

## Current terms

### Proposal

A **proposal** is a structured suggestion created by an AI agent. It is not a
command and does not change the test, source code, or test result by itself.

**Tiếng Việt:** **Proposal (đề xuất)** là gợi ý có cấu trúc do AI tạo ra. Nó
không phải lệnh thực thi và tự nó không được phép đổi test, mã nguồn hoặc kết
quả test.

Example: after a failed Playwright test, an agent may propose that the locator
for the `Submit` button changed from `#submit` to a button with accessible name
`Submit order`. The proposal contains its reasoning, evidence, confidence, and
the suggested change. A named human must explicitly approve or reject it.

**Ví dụ tiếng Việt:** Khi test thất bại, AI có thể đề xuất locator của nút
`Submit` đã đổi. Đề xuất nêu lý do, evidence, độ tin cậy và thay đổi gợi ý;
người có tên/đủ quyền phải approve hoặc reject rõ ràng.

Related terms:

- **Approval:** the recorded final decision by an authorized human about a
  proposal. Approval authorizes a reviewable change process; it does not make a
  failed test pass.
- **Deterministic rerun:** a normal, repeatable test execution by the runner
  after an approved change. Its result, not the AI's claim, validates a healing.
- **Verdict:** the runner's final status for a run: `passed`, `failed`,
  `errored`, or `skipped`.

- **Approval (phê duyệt):** quyết định cuối cùng được ghi nhận của người có
  quyền cho một proposal. Approval cho phép quy trình reviewable change, không
  làm một test fail tự thành pass.
- **Deterministic rerun (chạy lại xác định):** chạy test bình thường, lặp lại
  được bằng runner sau khi thay đổi được duyệt. Kết quả runner, không phải lời
  AI, mới xác nhận healing có hợp lệ.
- **Verdict (phán quyết/kết quả cuối):** trạng thái cuối từ runner: `passed`,
  `failed`, `errored`, hoặc `skipped`.

### Deterministic

An operation is **deterministic** when the system follows explicit code and
rules, producing a result based on observable execution rather than an AI's
judgment. In this platform, Playwright assertions determine the test verdict.

**Tiếng Việt:** **Deterministic (xác định)** nghĩa là hệ thống thực hiện theo
code và quy tắc tường minh, kết quả dựa trên việc chạy quan sát được chứ không
dựa vào phán đoán AI. Ở đây assertion của Playwright quyết định verdict.

### Runner

A **runner** is the component that performs a test. The initial runner is the
TypeScript Playwright worker; future API and Game runners must use the same
versioned execution contract.

**Tiếng Việt:** **Runner (bộ thực thi test)** là thành phần trực tiếp chạy test.
Runner đầu tiên là Playwright worker TypeScript; các runner API/Game sau này vẫn
phải dùng cùng execution contract đã versioned.

### Correlation ID

A **correlation ID** is one identifier carried by all records and messages
created for the same user action/run. It lets us connect an API request, DB
record, worker log, artifact, event, and proposal while debugging.

**Tiếng Việt:** **Correlation ID** là một mã được mang theo trong mọi bản ghi và
message của cùng một hành động/lần chạy. Nó nối API request, DB, worker log,
artifact, event và proposal khi cần trace lỗi.

### Artifact

An **artifact** is evidence produced by an execution, such as a screenshot,
video, Playwright trace, console log, or report. Binary artifacts live in MinIO;
the database stores their metadata, URI, and checksum.

**Tiếng Việt:** **Artifact (bằng chứng đầu ra)** là screenshot, video,
Playwright trace, console log hoặc report do lúc chạy tạo ra. File nhị phân nằm
trong MinIO; DB chỉ lưu metadata, URI và checksum.

### Revision

A **revision** is the immutable version of test/source code being run, normally
a Git commit SHA. It makes a result reproducible: we know exactly which test and
application version created it.

**Tiếng Việt:** **Revision (phiên bản bất biến)** là phiên bản code test/source
được chạy, thường là Git commit SHA. Nó giúp tái lập kết quả vì biết chính xác
test và ứng dụng ở phiên bản nào đã tạo kết quả đó.

### Idempotency key

An **idempotency key** identifies one intended request. Sending the same request
again with the same key must not create a second run or a second approval.

**Tiếng Việt:** **Idempotency key (khóa chống xử lý trùng)** nhận diện một yêu
cầu dự định. Gửi lại cùng request với cùng khóa không được tạo thêm run hay
approval thứ hai.
