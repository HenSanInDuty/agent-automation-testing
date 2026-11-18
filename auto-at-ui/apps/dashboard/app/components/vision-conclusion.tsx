import type { VisionExplorationConclusion } from "../generation-types";

export function VisionConclusion({ conclusion }: { conclusion?: VisionExplorationConclusion }) {
  if (!conclusion) return <div aria-label="Kết luận">
    <h2>Kết luận</h2><p>Chưa đủ dữ liệu để tổng hợp kết luận cho phiên này.</p>
    <p>Các thao tác đã ghi nhận chưa xác nhận chức năng của website hoạt động đúng.</p>
  </div>;
  const target = ["buttons", "visual_buttons"].includes(conclusion.interaction_scope) ? "nút" : "phần tử tương tác";
  const title = {
    completed: "Đã hoàn tất khám phá các phần tử đã ghi nhận trong phạm vi yêu cầu.",
    partial: "Chưa hoàn tất khám phá trong phạm vi yêu cầu.",
    cancelled: "Phiên đã bị hủy; kết quả dưới đây chỉ phản ánh phần đã thực hiện.",
    in_progress: "Đang khám phá; chưa có kết luận cuối cùng.",
  }[conclusion.status];
  return <div aria-label="Kết luận">
    <h2>Kết luận</h2>
    <p><strong>{title}</strong></p>
    {conclusion.interaction_scope === "buttons" && <p>Ph?m vi phi?n c?: ch? n?t HTML; ch?a bao g?m li?n k?t d?ng n?t v? n?t t?y bi?n.</p>}
    {conclusion.observed_controls !== null
      ? <p>Đã thao tác và ghi nhận kết quả trên <strong>{conclusion.completed_controls}/{conclusion.observed_controls} {target}</strong> đã nhận diện. Còn {conclusion.remaining_controls} {target} chưa có thao tác hoàn tất.</p>
      : <p>Không có danh sách phần tử đủ tin cậy để xác định số lượng đã kiểm tra và còn lại.</p>}
    {conclusion.interaction_scope === "visual_buttons" && conclusion.control_kinds && <p>{conclusion.control_kinds.native ?? 0} n?t HTML ? {conclusion.control_kinds.styled_link ?? 0} li?n k?t d?ng n?t ? {conclusion.control_kinds.custom ?? 0} n?t t?y bi?n.</p>}
    <p>{conclusion.operations_completed} thao tác hoàn tất · {conclusion.operations_failed} lỗi · {conclusion.operations_rejected} bị từ chối · {conclusion.operations_unknown} chưa rõ kết quả.</p>
    {conclusion.operations_pending > 0 && <p>{conclusion.operations_pending} thao tác chưa có kết quả cuối cùng.</p>}
    {conclusion.candidates_not_attempted > 0 && <p>{conclusion.candidates_not_attempted} đề xuất chưa được thực hiện.</p>}
    {conclusion.inventory_limited && <p>Một số phần tử chưa được nhận diện an toàn hoặc danh sách bị giới hạn; chưa xác nhận đủ phạm vi kiểm tra.</p>}
    <p><strong>Chức năng website: chưa được xác nhận đúng/sai.</strong> Kết quả này ghi nhận việc thao tác trong phạm vi đã khám phá. Cần đối chiếu hành vi mong đợi của từng nút để kết luận chức năng đạt hay không đạt.</p>
  </div>;
}
