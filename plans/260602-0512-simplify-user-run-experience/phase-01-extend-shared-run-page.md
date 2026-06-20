---
phase: 1
title: Extend Shared Run Page
status: completed
priority: P1
effort: 2h
dependencies: []
---

# Phase 1: Extend Shared Run Page

## Overview

Thêm 3 prop optional vào shared `PipelineRunPage` để bật chế độ "đơn giản hoá cho user". Mặc định tất cả `false`/`undefined` → hành vi y hệt hiện tại → **admin không đổi**.

## Requirements

- Functional:
  - `hideLlmProfile` → ẩn `<section>` LLM Profile (LLMProfileSelector). `llmProfileId` vẫn giữ state mặc định `null` → start run gửi `undefined` → backend dùng **System Default**.
  - `hideRunControls` → ẩn khối `<PipelineControls>` (Pause/Cancel) ở cột trái.
  - `showResultsInline` → khi run terminal (completed/failed/cancelled), render `<ResultsViewer run={runData} templateNodes={...} />` ngay trong cột phải, ngay dưới `TerminalSummaryCard`.
- Non-functional: không phá vỡ flow admin; không thêm dependency mới; file vẫn < ~900 dòng (đã 855 — chỉ thêm nhánh điều kiện, không tách file ở phase này).

## Architecture

`PipelineRunPage` đã có sẵn mọi dữ liệu cần:
- `runData` = `usePipelineRun(activeRunId)` → đúng kiểu `PipelineRunResponse` mà `ResultsViewer` cần.
- `template.nodes` (`PipelineNodeConfig[]`) → map sang `templateNodes` của ResultsViewer.

`ResultsViewer` signature (verified `ResultsViewer.tsx:44,883`):
```ts
interface ResultsViewerProps {
  run: PipelineRunResponse;
  templateNodes?: Array<{ node_id: string; label: string; node_type: string; enabled: boolean }>;
}
```

Render inline đặt trong nhánh `isTerminalRun` hiện có (`PipelineRunPage.tsx:830-838`), bổ sung `ResultsViewer` sau `TerminalSummaryCard` khi `showResultsInline`.

## Related Code Files

- Modify: `packages/shared/src/components/pipeline/PipelineRunPage.tsx`
- Read for context: `packages/shared/src/components/pipeline/ResultsViewer.tsx` (props), `packages/shared/src/components/pipeline/PipelineRunDetailPage.tsx:594` (cách wire ResultsViewer + dựng templateNodes), `packages/shared/src/components/pipeline/PipelineControls.tsx`
- Do NOT touch: `apps/admin-app/src/components/pipeline/PipelineRunPage.tsx` (chỉ `export *`).

## Implementation Steps

1. Mở rộng interface `PipelineRunPageProps` (PipelineRunPage.tsx:540):
   ```ts
   export interface PipelineRunPageProps {
     templateId: string;
     /** Ẩn dropdown LLM Profile; luôn chạy bằng System Default. Mặc định false. */
     hideLlmProfile?: boolean;
     /** Ẩn nút Pause/Cancel khi đang chạy. Mặc định false. */
     hideRunControls?: boolean;
     /** Render full ResultsViewer inline sau khi run kết thúc. Mặc định false. */
     showResultsInline?: boolean;
   }
   ```
   Destructure với default: `{ templateId, hideLlmProfile = false, hideRunControls = false, showResultsInline = false }`.
2. Import `ResultsViewer`: `import { ResultsViewer } from "./ResultsViewer";` (cùng thư mục).
3. Bọc `<section>` LLM Profile (dòng ~769-782) trong `{!hideLlmProfile && ( ... )}`.
4. Bọc khối `<PipelineControls>` (dòng ~807-820) trong điều kiện thêm `!hideRunControls &&` (giữ nguyên các điều kiện cũ `hasActiveRun && !isTerminal && ...`).
5. Dựng `templateNodes` (memo hoá) từ `template.nodes`:
   ```ts
   const templateNodes = React.useMemo(
     () => (template?.nodes ?? []).map((n) => ({
       node_id: n.node_id, label: n.label, node_type: n.node_type, enabled: n.enabled ?? true,
     })),
     [template],
   );
   ```
   (Đối chiếu cách `PipelineRunDetailPage` build `templateNodes` để khớp field `enabled`.)
6. Trong cột phải, sau `<TerminalSummaryCard>` (dòng ~838), thêm:
   ```tsx
   {isTerminalRun && showResultsInline && runData && (
     <ResultsViewer run={runData} templateNodes={templateNodes} />
   )}
   ```
7. (Tùy chọn copy nhỏ) Khi `hideLlmProfile`, chỉnh text gợi ý trong `NoRunPlaceholder` ("pick an LLM profile") cho khỏi lệch — chỉ làm nếu nhanh, không bắt buộc.
8. Chạy typecheck workspace shared để chắc không lỗi type (`npm --workspace @auto-at/shared run build` hoặc `tsc`); xem Phase 3.

## Todo List

- [ ] Thêm 3 prop vào `PipelineRunPageProps` + destructure default
- [ ] Import `ResultsViewer`
- [ ] Ẩn LLM Profile theo `hideLlmProfile`
- [ ] Ẩn PipelineControls theo `hideRunControls`
- [ ] Memo `templateNodes` từ `template.nodes`
- [ ] Render `ResultsViewer` inline theo `showResultsInline`
- [ ] Typecheck shared không lỗi

## Success Criteria

- [ ] Gọi `<PipelineRunPage templateId=... />` (không props) → render y hệt hiện tại (admin path không đổi).
- [ ] Bật cả 3 prop → ẩn LLM Profile + Pause/Cancel, và hiện ResultsViewer inline khi run xong.
- [ ] Không có lỗi TypeScript trong `packages/shared`.

## Risk Assessment

- **Run gửi `llmProfileId=undefined` khi ẩn selector** → cần backend có System Default. Đã verify selector mặc định `null` → `undefined`; hành vi này vốn đã hợp lệ (option "System Default" hiện có). Mitigation: không đổi logic `handleRun`, chỉ ẩn UI.
- **ResultsViewer tự fetch `getRunResults`** (node outputs) → inline render kích thêm 1 query; chấp nhận được, chỉ chạy khi terminal.
- **File dài thêm** → vẫn nhánh điều kiện nhỏ; nếu vượt ngưỡng cân nhắc tách ở phase sau (YAGNI: chưa cần).
