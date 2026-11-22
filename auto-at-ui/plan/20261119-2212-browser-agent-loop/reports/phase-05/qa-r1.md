STATUS: PASS

QA phase 5 (Dashboard). Chi tiết: `plan/20261119-2212-browser-agent-loop/qa/phase-05/test-report.md` và `test-cases.md`.

- Unit 49/49 (thêm 1 case QA), typecheck 0, lint 0, build 0 (chạy trực tiếp node thay `pnpm` vì pnpm không có trong PATH).
- E2E: 55 pass / 2 fail (spec:238, spec:336, `toBeInViewport` viewport ratio 0). Baseline HEAD (git worktree tạm, đã gỡ): cả 2 đỏ y hệt => sẵn có, không phải hồi quy phase 5.
- 3 e2e mới của phase xanh (gating/payload engine, ledger agent_step + planner không có khối, 400px không tràn).
- Cảnh báo: `hgraph check --changed` exit 1 do 48 file `uncovered-changed` mang tiền tố `auto-at-ui/` (artifact đường dẫn, git root ở thư mục cha); `hgraph check` theo file cho 6 file phase 5 sạch. Leader quyết định.
- Đã dọn: server 3107, worktree, junction (node_modules thật còn nguyên).
- File test QA sửa: `apps/dashboard/app/components/vision-provider-model.test.ts` (thêm 1 test).
