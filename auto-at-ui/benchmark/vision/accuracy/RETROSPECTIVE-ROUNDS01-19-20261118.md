# Rà soát 19 vòng Vision — 2026-11-18

**Dừng trước vòng 20 theo yêu cầu người dùng.** Chỉ đọc dữ liệu đã lưu; không chạy
browser, model, deploy hay thay đổi runtime/oracle/điểm lịch sử trong đợt rà soát này.

Kết luận: hệ thống đã tiến bộ về số mục tiêu đi tới được, nhưng chưa có accuracy
ổn định. Những vòng cuối tiếp tục gặp ba vấn đề: proposal/checkpoint hết hiệu lực
trên UI động, cùng một video path ngoài oracle bị click lại, và ảnh kết quả bị
chụp sau khi carousel tự đổi slide. Sửa lỗi dừng cuối phiên giúp chạy xa hơn nhưng
không tự giải quyết hai nguyên nhân làm mất điểm ở gần ngưỡng 95%.

## Phạm vi và cách đọc số liệu

Đối chiếu đủ 19 manifest, evidence, assessments, score; đọc thêm review-status,
review bổ sung, mismatch, telemetry, ADR và nhật ký kế hoạch. Có 20 thư mục run:
một là baseline lịch sử được import, **không tính thành vòng 01**. Bản tổng hợp
[JSON](retrospective-rounds01-19-20261118.json) giữ ID, source/policy, số liệu và
SHA-256 các đầu vào để đối soát. Không tải lại ảnh đã được review.

- `completed` chỉ chứng minh thao tác hoàn tất, không chứng minh đúng kết quả.
- Vòng 16 là vòng duy nhất đạt điểm đã thẩm định: accuracy 46/48, coverage 46/47.
  Vòng 17–18 review một phần; vòng 15 có sáu review carousel bổ sung nhưng giữ
  nguyên điểm cận dưới trước đó. Các vòng còn lại không xác lập outcome accuracy.
- Điểm 0 hoặc 5 được lưu khi ngừng review sau một gate chắc chắn thất bại là
  **cận dưới đã xác minh**, không phải tỷ lệ đúng thực tế. Không thể vẽ một đường
  accuracy từ 19 trường `score.accuracy.percent` rồi suy ra xu hướng chất lượng.
- Source thay đổi qua nhiều vòng; limits đổi từ 50 states/10 hops sang 100/20
  trước vòng 06. `config_hash` giống nhau không đủ chứng minh limits giống nhau:
  cần đối chiếu `observed_policy` và provenance. Vòng 16 và 17 cùng source/policy
  là đối chiếu có ý nghĩa nhất về tính lặp lại.

| Vòng | Click thử / binding đủ điều kiện | Lý do dừng | Kết luận về điểm |
|---:|---:|---|---|
| [01](runs/7b45b398-fd6a-442b-b534-0ce0f79365de/manifest.json) | 22 / 22 | `state_restore_failed` | Coverage tối đa 22/47; accuracy chưa xác lập |
| [02](runs/d2c0d660-1309-4dab-85f3-fbb777e2b19d/manifest.json) | 26 / 26 | `exploration_coverage_incomplete` | Coverage tối đa 26/47; accuracy chưa xác lập |
| [03](runs/dab64d78-48cd-4b3b-ae85-4f34bf482a30/manifest.json) | 20 / 20 | `unsafe_replay` | Coverage tối đa 20/47; accuracy chưa xác lập |
| [04](runs/aee8f4a3-d93f-4e81-b3fd-3627f36dce48/manifest.json) | 10 / 10 | `state_changed_during_prepare` | Coverage tối đa 10/47; accuracy chưa xác lập |
| [05](runs/b06acee8-f9c9-4d80-bc09-10ddd6f524d0/manifest.json) | 35 / 35 | `unsafe_replay` | Coverage tối đa 35/47; accuracy chưa xác lập |
| [06](runs/f37c0b20-bf2f-4e24-a125-0ba8f820f186/manifest.json) | 37 / 37 | `unsafe_replay` | Coverage tối đa 37/47; accuracy chưa xác lập |
| [07](runs/e1f4a3a4-56fb-40ec-b423-4c0e231eb78b/manifest.json) | 33 / 33 | `unsafe_replay` | Coverage tối đa 33/47; accuracy chưa xác lập |
| [08](runs/db377eba-12b1-4db4-84d1-3734e2bf1f25/manifest.json) | 15 / 15 | `state_mismatch` | Coverage tối đa 15/47; accuracy chưa xác lập |
| [09](runs/65e78e75-5665-4dda-ac13-59a1f4ce60b2/manifest.json) | 26 / 26 | `bridge_offline` | Coverage tối đa 26/47; accuracy chưa xác lập |
| [10](runs/90e66243-ed11-4163-85bd-ae0ea401b9eb/manifest.json) | 39 / 34 | `unsafe_replay` | Coverage tối đa 34/47; accuracy chưa xác lập |
| [11](runs/827a7e61-5752-4ab5-b8ab-43e69bd70ffc/manifest.json) | 17 / 17 | `bridge_provider_unavailable` | Coverage tối đa 17/47; accuracy chưa xác lập |
| [12](runs/15967ed1-c9b7-43ad-8878-41e68b414d23/manifest.json) | 35 / 35 | `unsafe_replay` | Coverage tối đa 35/47; accuracy chưa xác lập |
| [13](runs/5556d5db-bae4-4571-b2bb-d99d171ab8da/manifest.json) | 0 / 0 | `visual_exploration_unavailable` | Không có thao tác |
| [14](runs/1de7b316-99d0-4a3a-9e02-dd684a23df60/manifest.json) | 30 / 30 | `unsafe_replay` | Coverage tối đa 30/47; accuracy chưa xác lập |
| [15](runs/aded2b83-bfc6-4c99-8461-d829e002a9b6/manifest.json) | 49 / 46 | `unsafe_replay` | Trần bằng chứng 46/49 = 93.88% |
| [16](runs/fd3ddda4-ca69-4abb-818b-a8ac1ad594d8/manifest.json) | 48 / 46 | `unsafe_replay` | Đã review: 46/48 = 95,83%; đạt một vòng |
| [17](runs/56e50d4d-2be0-433b-98ad-2eab68d7773f/manifest.json) | 47 / 45 | `unsafe_replay` | Trần bằng chứng 44/47 = 93.62% |
| [18](runs/1f13a1e9-d08d-4582-8f3a-bfae43be833e/manifest.json) | 15 / 15 | `state_restore_failed` | Coverage tối đa 14/47; ảnh slide không khớp |
| [19](runs/9f84261c-0d0f-47c6-894c-d476f72d9bf1/manifest.json) | 49 / 46 | `unsafe_replay` | Trần bằng chứng 46/49 = 93.88% |

Binding đủ điều kiện trong bảng là completed + verified locator + positive path
trong oracle. Nó chưa bao gồm việc xác minh kết quả. Trần ở vòng 17 đã trừ ảnh
carousel không khớp; trần vòng 15/19 chỉ dựa vào binding. Mọi rejected attempt
vẫn nằm trong mẫu số.

## Lỗi tái diễn và mức độ chứng minh

### 1. Quay về trạng thái cũ trên giao diện đã thay đổi — 11/19 vòng dừng

Các vòng **03, 05, 06, 07, 10, 12, 14, 15, 16, 17, 19** kết thúc bằng
`unsafe_replay`. Trong đó **05, 06, 07, 10, 15, 16, 17, 19** có operation ghi
`history_checkpoint_unavailable`. Đây là cùng họ lỗi, không phải bằng chứng rằng
cả 11 vòng có một nguyên nhân vi mô duy nhất:

- 03: một click tạo hai history entries; Back thường chưa về nguồn.
- 05: UI đổi không tạo history entry, đồng thời chạm hop cap.
- 06–07: sibling proposals còn gắn checkpoint cũ; ảnh hưởng lan sang viewport khác.
- 10: đổi tab Mounts làm bốn character controls bị thay trước khi click.
- 12: Back + refresh không tái lập checkpoint; dữ liệu lúc đó chưa đủ chỉ ra trường lệch.
- 14: nguồn ở y=0, Back về y=576; cần đối soát scroll sau Back.
- 15–17, 19: tiếp tục thất bại ở checkpoint cũ cuối phiên; vòng 19 có interaction/
  visual-semantics drift trong khi URL, forms và scroll giữ nguyên.

ADR-025/027/030/032 đã sửa các trường hợp có thật. Tuy nhiên code hiện vẫn dùng
queue các nhánh/checkpoint và phục hồi nhánh trước khi thực thi. Điều kiện
invalidation tại `vision_trace_events.py` quanh dòng 1306 dựa trên một số dấu hiệu
mutation cụ thể; heuristic xếp thứ tự ở ADR-030 không chứng minh các action độc lập.
**Suy luận kiến trúc:** UI động cần quản lý vòng đời proposal theo trạng thái hiện
tại rõ ràng hơn; Back không thể khôi phục mọi lựa chọn tab/carousel nội bộ.

Lưu ý tác động điểm: restore không nằm trong mẫu số click accuracy. Nó làm mất
coverage nếu dừng sớm, nhưng không tự làm vòng 16 fail benchmark khi điểm đã đủ.
Vì vậy chỉ sửa terminal restoration chưa chắc tăng accuracy ở vòng 19.

### 2. Cùng một video path ngoài oracle và target động — trực tiếp chặn accuracy

Vòng **15, 16, 17, 19** có completed click vào **cùng một path** không khớp
oracle: operation **101, 104, 102, 101** tương ứng. Cả bốn đều thiếu completed
positive binding cho `mct-47`; vòng 17 còn thiếu `mct-21`.

Path ngoài oracle dùng nhánh `div:nth-of-type(4)` ở vị trí mà mct-47 tham chiếu
`div:nth-of-type(3)`. Review bổ sung vòng 15 chỉ thấy video overlay, chưa xác lập
đúng declared video. Không đủ bằng chứng để tự xem hai path là cùng target hay
quy kết mọi click này là click nhầm vật lý. Theo oracle đã đóng băng, chúng không
được nhận điểm. Exact identity/destination của từng copy là việc cần làm rõ.

Các vòng **10, 15, 16, 17, 19** còn có explore-click bị `stale_dom_target` hoặc
`unsupported_target`. Guard đã chặn thao tác không đủ điều kiện; vấn đề upstream
là proposal/target không còn hợp lệ khi tới bước thực thi.

- 15 và 19 đều: **46 eligible / 49 attempts = 93,8776% tối đa**.
- 16: **46 correct / 48 attempts = 95,8333%**, chỉ qua ngưỡng nhờ ít hơn một
  attempt không được nhận điểm so với hai vòng trên. Chưa giải quyết mct-47.
- 17: 45 eligible/47; một ảnh slide không khớp làm trần bằng chứng còn **44/47**.

Đây là nút thắt accuracy có bằng chứng trực tiếp. Cần sửa chất lượng target và
proposal trước dispatch bằng quy tắc runtime tổng quát; không hard-code bỏ path
theo oracle, không xóa attempt đã xảy ra, không tự gộp các vị trí oracle khác nhau.

### 3. Bằng chứng carousel bị trễ — xác nhận vòng 17–18, định vị thời gian vòng 19

- 17: operation 26 yêu cầu slide 4, after-frame là slide 5.
- 18: operation 24 yêu cầu slide 3, after-frame là slide 4, dù đã có ADR-034.
- 19: cả **23 sample sớm bị loại**: 5 hết giờ settle, 16 timeout screenshot,
  2 hết giờ verify; **0 reuse**. Sáu sample carousel: settle 221–325 ms; hai mẫu
  hoàn tất verify ở 543/616 ms, bốn mẫu còn lại timeout capture. Budget tổng 500 ms.

Đây là chứng cứ cách lấy sample sớm chưa hiệu quả trên tải thật. Fixture nhẹ pass
không bảo đảm chuỗi inspect/settle/PNG/verify chạy kịp trong worker thật. Vòng 19
chưa review ảnh carousel, nên không được nói cả sáu outcome đều sai. Cũng không
có bằng chứng các mismatch này do click nhầm vật lý; autoplay/timing là giả thuyết
được fixture và telemetry hỗ trợ, nhưng từng live outcome vẫn phải được review.

### 4. Popup hydrate giữa các bước — bốn lần dừng, khác ô trong cùng ma trận

| Vòng | Thao tác / thời điểm | Triệu chứng |
|---:|---|---|
| 01 | close_popup / before_dispatch | interaction và visual state đổi |
| 04 | refresh wait / prepare_end | form presence/values đổi |
| 08 | refresh wait / before_dispatch | form presence/values đổi |
| 18 | close_popup / prepare_end | form presence/values đổi |

Các bản sửa lần lượt mở rộng recovery có bằng chứng no-dispatch. Việc một ô được
sửa rồi lỗi xuất hiện ở ô khác cho thấy cần kiểm thử đầy đủ action × stage ×
mutation, thay vì dùng việc đi qua một điểm dừng để suy ra đã xử lý cả họ lỗi.
Vòng 19 đóng 21 popup thành công nhưng **không có prepare rejection**, nên không
chứng minh hiệu quả live của nhánh mới ADR-035; chỉ có synthetic red/green cho nó.

### 5. Các gián đoạn khác — có thật, nhưng không giải thích trần gần đây

Vòng 09 bridge heartbeat/offline, 11 provider unavailable, 13 HTTP worker chưa
sẵn sàng: **3/19 vòng**. Vòng 02 hết hop budget: **1/19**. Capacity đã được nâng
sau direction của người dùng trước vòng 06; các vòng gần đây không cho thấy tăng
model/caps tiếp sẽ xử lý lỗi video path hoặc ảnh trễ. Chưa có bằng chứng cần đổi model.

## Vì sao cách lặp vừa qua không còn tạo tiến bộ rõ

1. **Ưu tiên lỗi cuối phiên thay vì lỗi mất điểm lặp nhiều nhất.** Bản sửa popup/
   restoration giúp chạy xa hơn, nhưng path video ngoài oracle tồn tại từ vòng
   15 tới 19; hai vòng này có cùng trần 46/49.
2. **Synthetic green được dùng để bước sang live quá sớm về mặt giả thuyết.**
   Test bảo vệ guard tốt, nhưng fixture capture nhẹ không tái hiện chi phí DOM/PNG
   của trang thật. Lượt live sau đó trở thành phép đo hiệu năng đầu tiên.
3. **Một lần pass chưa chứng minh ổn định.** Vòng 16 và 17 dùng cùng source nhưng
   kết quả khác nhau. Không có A/B kiểm soát đủ để tách đóng góp của model order,
   autoplay, hydration và timing; không thể gán toàn bộ thay đổi điểm cho patch.
4. **Thiếu bảng xu hướng phân biệt cận dưới, trần và điểm đã review.** Quyết định
   dừng review khi chắc chắn fail tiết kiệm chi phí hợp lý, nhưng cần báo riêng
   trạng thái đo. Detection trên 95% ở cả 18 vòng có browser cho thấy không nên
   dùng detection như proxy cho outcome accuracy.

## Hướng xử lý đề xuất trước khi cho chạy vòng 20

1. **Ưu tiên target/proposal và video copies:** dựng fixture nhiều copy, thay node,
   chuyển tab và autoplay theo các trace 15–19; xác minh identity/destination độc
   lập, vòng đời proposal, khả năng click thực tế và re-observation. Đo số attempt
   ngoài scope/stale/unsupported; giữ mọi guard và toàn bộ lịch sử denominator.
2. **Song song về phạm vi thiết kế, chưa triển khai trong audit này: capture trên
   tải đại diện.** Fixture DOM/PNG và CPU quota tương đương worker; đo từng stage
   trong budget hiện tại, chứng minh retained frame chứa trạng thái lựa chọn ngay
   sau click và fallback đúng khi form/navigation/target đổi. Tối ưu đo đạc trước
   khi đề xuất đổi policy; không tắt autoplay để làm benchmark dễ hơn.
3. **Rà lại cơ chế trạng thái và recovery theo ma trận.** Phân biệt checkpoint
   phục hồi thật được với trạng thái UI không có history; proposal cũ kết thúc
   có audit, proposal mới phải dựa trên observation mới. Kiểm đủ popup close/
   refresh × prepare/dispatch × form/node/page drift và các giới hạn hiện tại.
4. Chỉ mở lại live khi fixture tái hiện được lỗi lặp và có bằng chứng sửa đúng
   trên tải đại diện. Khi đó dùng một candidate đóng băng, chấm độc lập; ba vòng
   liên tiếp >95% và tổng ≥100 attempts vẫn là tiêu chí đã thống nhất.

Các mục trên là đề xuất sau audit, chưa sửa runtime, chưa tự tạo vòng 20 và chưa
đổi oracle/model/policy. Đợt tiếp theo cần hướng vào hai nút thắt mất điểm trực tiếp
trước khi kỳ vọng chữa restoration sẽ làm accuracy tăng.

## Sai khác tài liệu phát hiện khi đối soát

Nhật ký cũ ghi vòng 09 có 25 completed clicks, nhưng `evidence.json`,
`assessments.json`, `review-status.json` thống nhất **26**. Audit dùng 26, giữ
nguyên artifacts lịch sử và ghi correction tại đây/JSON. Sai khác này không đổi
kết luận fail vì coverage vẫn không thể đạt 45/47.
