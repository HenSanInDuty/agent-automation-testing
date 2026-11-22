import type { VisionExplorationConclusion } from "../generation-types";

const body = "text-sm text-pretty text-muted-foreground";

export function VisionConclusion({ conclusion }: { conclusion?: VisionExplorationConclusion }) {
  if (!conclusion) return <div aria-label="Kết luận" className="grid gap-2 rounded-lg border border-l-4 border-l-muted-foreground bg-muted/40 px-4 py-3">
    <h2 className="text-sm font-semibold tracking-tight">Kết luận</h2><p className={body}>Chưa đủ dữ liệu để tổng hợp kết luận cho phiên này.</p>
    <p className={body}>Các thao tác đã ghi nhận chưa xác nhận chức năng của website hoạt động đúng.</p>
  </div>;
  const target = ["buttons", "visual_buttons"].includes(conclusion.interaction_scope) ? "nút" : "phần tử tương tác";
  const title = {
    completed: "Đã hoàn tất khám phá các phần tử đã ghi nhận trong phạm vi yêu cầu.",
    partial: "Chưa hoàn tất khám phá trong phạm vi yêu cầu.",
    cancelled: "Phiên đã bị hủy; kết quả dưới đây chỉ phản ánh phần đã thực hiện.",
    in_progress: "Đang khám phá; chưa có kết luận cuối cùng.",
  }[conclusion.status];
  const accent = { completed: "border-l-success", partial: "border-l-warning", cancelled: "border-l-muted-foreground", in_progress: "border-l-info" }[conclusion.status];
  return <div aria-label="Kết luận" className={`grid gap-2 rounded-lg border border-l-4 bg-muted/40 px-4 py-3 ${accent}`}>
    <h2 className="text-sm font-semibold tracking-tight">Kết luận</h2>
    <p className="text-sm text-foreground"><strong>{title}</strong></p>
    {conclusion.interaction_scope === "buttons" && <p className={body}>Phạm vi phiên cũ: chỉ nút HTML; chưa bao gồm liên kết dạng nút và nút tùy biến.</p>}
    {conclusion.observed_controls !== null
      ? <p className={body}>Đã thao tác và ghi nhận kết quả trên <strong className="text-foreground">{conclusion.completed_controls}/{conclusion.observed_controls} {target}</strong> đã nhận diện. Còn {conclusion.remaining_controls} {target} chưa có thao tác hoàn tất.</p>
      : <p className={body}>Không có danh sách phần tử đủ tin cậy để xác định số lượng đã kiểm tra và còn lại.</p>}
    {conclusion.interaction_scope === "visual_buttons" && conclusion.control_kinds && <p className={body}>{conclusion.control_kinds.native ?? 0} nút HTML · {conclusion.control_kinds.styled_link ?? 0} liên kết dạng nút · {conclusion.control_kinds.custom ?? 0} nút tùy biến.</p>}
    <p className={body}>{conclusion.operations_completed} thao tác hoàn tất · {conclusion.operations_failed} lỗi · {conclusion.operations_rejected} bị từ chối · {conclusion.operations_unknown} chưa rõ kết quả.</p>
    {conclusion.operations_pending > 0 && <p className={body}>{conclusion.operations_pending} thao tác chưa có kết quả cuối cùng.</p>}
    {conclusion.candidates_not_attempted > 0 && <p className={body}>{conclusion.candidates_not_attempted} đề xuất chưa được thực hiện.</p>}
    {conclusion.inventory_limited && <p className={body}>Một số phần tử chưa được nhận diện an toàn hoặc danh sách bị giới hạn; chưa xác nhận đủ phạm vi kiểm tra.</p>}
    <p className={body}><strong className="text-foreground">Chức năng website: chưa được xác nhận đúng/sai.</strong> Kết quả này ghi nhận việc thao tác trong phạm vi đã khám phá. Cần đối chiếu hành vi mong đợi của từng nút để kết luận chức năng đạt hay không đạt.</p>
  </div>;
}
