STATUS: DONE

# PM r1 - trả lời 2 câu ASK_PM của be-developer (phase 1, browser-agent-loop)

Không sửa code/plan. Không cần user quyết (không có quyết định nghiệp vụ); phiên chính chỉ cần áp các sửa plan bên dưới.

## Câu 1 - request.json 16 384 byte vs `AgentLoopContext.snapshot` 24 000 ký tự

Căn cứ code:
- Đọc: `infrastructure/codex_bridge/spool.py:244-246` `read_file(directory, "request.json", 16_384)`. Ghi: `spool.py:294` cho phép 65 536 với mọi file trừ screenshot. Hai giới hạn đã lệch nhau sẵn; 16 384 chỉ là trần chống đọc quá to, không phải bất biến bảo mật (request đã bị ràng buộc bởi hash trong `CodexBridgeResponse.request_hash` và `_scope`).
- `canonical_bytes` dùng `ensure_ascii=False` (`contracts/codex_bridge.py:52-55`) => tiếng Việt 2-3 byte/ký tự. Snapshot 24 000 ký tự tới ~72 000 byte; cộng task 4 000 + memory 2 000 + history 5x600 + `allowed_hosts` 100x255 => worst case ~100-125 KB. Tức là 65 536 ở ghi (`:294`) cũng KHÔNG đủ; chỉ nâng đọc lên 65 536 là chưa xong.
- v4: request.json bị chặn bởi `CodexTaskContext` <= 8 192 byte + trường cố định => luôn < 16 KB, nên nâng trần không đổi byte nào của job v4 (agent_context bị bỏ khỏi serialize, `codex_bridge.py:250-256`).
- `generation_spool.py:20` có giới hạn 16 384 riêng cho job generation: không liên quan, không đụng.

Quyết định: **(a) nâng trần request.json, nhưng dùng giới hạn theo tên file và thêm chốt sớm ở contract**:
1. `spool.py`: hằng `REQUEST_MAX_BYTES = 131_072`; dùng ở `:245` (đọc) và `:294` (ghi: request.json dùng hằng này, dom/schema giữ 65 536, screenshot giữ 5 000 000).
2. `contracts/codex_bridge.py`: trong `CodexBridgeRequest.valid_job` thêm `len(canonical_bytes(self)) <= 131_072` chỉ khi có `agent_context` (fail-fast ở lúc dựng request, không phải lúc publish). Giữ `AGENT_SNAPSHOT_MAX_CHARS = 24_000` (AC5 đo bằng `len(str)` giữ nguyên).
3. Test: round-trip `publish` -> `load` một request agent snapshot 24 000 ký tự tiếng Việt (3 byte/ký tự); request v4 vẫn bị `load` từ chối nếu file > 16 384? -> KHÔNG: giới hạn chung nâng nên không còn từ chối; thay bằng khẳng định byte v4 không đổi (fixture `v4_identity.json`).

Vì sao không chọn (b)/(c):
- (b) tách file: thêm tên vào `FILES` (`spool.py:39`), thêm trường hash vào `CodexInputHashes` (đổi contract v4 hoặc phải omit-if-absent), thêm đường verify/chown/publish và test integrity => đụng v4 nhiều nhất, nhiều hơn một dòng hằng số.
- (c) giới hạn byte: ép snapshot ~5 000 ký tự để vừa 16 KB => phá AC5 (24 000) và chất lượng snapshot (100 element), hoặc phải đổi AC5.

Phase/file bị ảnh hưởng:
- Phase 3 nhận `apps/control-plane/infrastructure/codex_bridge/spool.py` (thêm vào mục "Sửa") + test round-trip trong `tests/test_agent_loop_bridge.py`. Lý do chọn phase 3: phase 3 là phase đầu tiên gửi request agent thật qua spool; phase 1 không cần (be-developer đã nói không chặn phase 1).
- Phase 1 (vòng sửa r2, nhỏ): thêm validator kích thước 131 072 vào `packages/contracts/src/auto_at/contracts/codex_bridge.py` + 1 test trong `tests/test_agent_loop_contracts.py`. Nếu muốn giữ phase 1 sạch: chuyển validator sang phase 3 cùng với spool (cùng hằng số) - chấp nhận được, nhưng một hằng số hai file nên để cùng phase 3 thì đơn giản hơn; khuyến nghị: **cả hằng + validator ở phase 3** để không chạm lại contract phase 1 đã QA.
- Graph: `spool.py` thuộc graph `codex-bridge` (cập nhật bằng `hgraph check --changed`).
- Cần tra thêm ở phase 3 (chưa kiểm vì ngoài phạm vi câu hỏi): trần độ dài prompt/arg của Codex/Claude CLI với prompt ~100 KB (be-developer phase 3 đã có rủi ro "prompt quá dài" - thêm test độ dài ở đó).

## Câu 2 - `invalid_ref` vs `AgentRef` có `pattern` ở lúc parse

Căn cứ:
- `contracts/codex_bridge.py:369` `AgentRef = Annotated[str, Field(pattern=r"^[0-9]+:[0-9]+$", max_length=24)]`; `AgentAction.ref` dùng nó (`:388`). `parse_agent_output` (`:422-427`) dùng `TypeAdapter(...).validate_python` => 1 ref sai làm cả `AgentStep` (tới 10 action) bị `ValidationError`.
- v4 khi output hỏng: không retry, kết thúc (`application/vision_trace_events.py:740-754`, comment "Do not retry the model"). Với vòng lặp khép kín, mất cả bước + (nếu retry) tốn 1 trong 20 lần gọi chỉ vì một ref dị dạng là quá nặng; và AC2 + phase 4 bước 4 + test phase 4 `test_vision_agent_loop.py` đều đã viết "ref sai regex => invalid_ref, action vẫn nằm trong `actions` với `skipped_reason`" (AC1: action bị chặn có trong step log).
- Lưu ý: `agent_loop_output_schema()` (`:430-457`) sinh từ Pydantic, nên `pattern` hiện cũng nằm trong schema gửi provider (strict decoding hầu như không sinh ref sai). Bỏ `pattern` làm provider không còn ép định dạng.

Quyết định: **nới `ref` thành `str` có giới hạn độ dài, `invalid_ref` ở domain** (giữ AC2 nguyên văn, không sửa acceptance).
1. Phase 1 (vòng sửa r2, sửa nhỏ): `AgentRef = Annotated[str, Field(min_length=1, max_length=24)]`; xuất hằng `AGENT_REF_PATTERN = r"^[0-9]+:[0-9]+$"` ở contract làm nguồn duy nhất cho phase 4; cập nhật test trong `tests/test_agent_loop_contracts.py` (ref sai regex nay parse được; ref dài > 24 hoặc rỗng vẫn bị từ chối; schema vẫn strict). Giữ `fields_match_kind` nguyên.
2. Phase 4: `vision_agent_loop.py`/`vision_agent_safety.py` dùng `re.fullmatch(AGENT_REF_PATTERN, ref)` => không khớp thì `invalid_ref` (không gọi worker), khớp rồi mới kiểm `stale_ref`. Test phase 4 đã có đúng ca này, không đổi.
3. Phase 3: một dòng trong `INSTRUCTIONS` nói rõ định dạng ref `version:n` (vì schema không còn ép), thêm vào test prompt.
- Hệ quả chấp nhận: schema gửi provider mất `pattern`; model có thể trả ref dị dạng hiếm gặp => ghi `invalid_ref` vào step log và model thấy ở bước sau (đúng ý đồ closed loop).
- Phương án còn lại (coi parse lỗi = `model_output_invalid` và sửa AC2) bị loại: phải sửa plan.md AC2 + phase 4 test, mất bước và tính vào trần 20 lần gọi, ngược với triết lý "action bị chặn có trong `actions`".

Phase/file bị ảnh hưởng: phase 1 (`packages/contracts/src/auto_at/contracts/codex_bridge.py`, `tests/test_agent_loop_contracts.py`); phase 3 (`agents/prompts/agent_loop.py` + `tests/test_agent_loop_prompt.py`, 1 dòng/1 test); phase 4 (không đổi phạm vi, chỉ dùng `AGENT_REF_PATTERN`). plan.md AC2 giữ nguyên. Hash `CodexOutput`/`codex-dom-v11` không đổi (`AgentRef` chỉ thuộc họ agent).

## Sửa plan đề xuất cho phiên chính (không áp dụng ở đây)
- `phase-03-prompt-bridge.md`: thêm `infrastructure/codex_bridge/spool.py` (hằng `REQUEST_MAX_BYTES`, validator kích thước agent request nếu đặt ở phase 3) vào mục "Sửa"; thêm test round-trip 24 000 ký tự 3-byte; thêm dòng định dạng ref vào bước 1.
- `phase-01-contract-db-engine.md`: ghi vòng sửa r2 = nới `AgentRef` + xuất `AGENT_REF_PATTERN`.
- `plan.md` mục "Sửa sau review": thêm 2 dòng quyết định trên. Contract/AC không đổi.

## Câu hỏi thứ 3 của be-developer (ruff / file phase 0)
Không nằm trong yêu cầu lần này; không trả lời.

NEEDS_USER_INPUT: không có.
