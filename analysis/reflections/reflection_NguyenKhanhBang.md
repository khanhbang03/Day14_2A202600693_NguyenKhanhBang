# Reflection - Nguyen Khanh Bang

## 1. Engineering Contribution
Em phụ trách hoàn thiện pipeline đánh giá end-to-end cho Lab Day 14:
- Thiết kế synthetic golden dataset 55 cases với `expected_retrieval_ids`, gồm grounded cases và red-team cases.
- Xây dựng RAG agent offline có retrieval theo corpus, trả `retrieved_ids`, contexts, token usage và estimated cost.
- Triển khai async benchmark runner để chạy nhiều cases song song theo batch.
- Tích hợp retrieval metrics gồm Hit Rate và MRR.
- Xây dựng multi-judge consensus có real model judges (`gpt-4o-mini`, `gpt-4.1-mini` fallback khi Claude billing không khả dụng), agreement rate, conflict resolution, judge-mode audit và Cohen's Kappa bucketed.
- Thêm regression release gate so sánh Agent V1 và Agent V2 bằng quality, retrieval, latency và cost.
- Bổ sung position-bias calibration và red-team audit để báo cáo không chỉ có điểm trung bình mà còn có bằng chứng về độ tin cậy của evaluator.

## 2. Technical Depth
**Hit Rate** đo xem ít nhất một expected document có nằm trong top-k retrieval hay không. Metric này trả lời câu hỏi: "Retriever có lấy được bằng chứng đúng không?"

**MRR** đo vị trí của tài liệu đúng đầu tiên. Nếu tài liệu đúng đứng rank 1 thì MRR = 1.0; rank 2 thì 0.5. MRR quan trọng vì context đứng càng cao thì generator càng dễ dùng đúng bằng chứng.

**Cohen's Kappa / Agreement Thinking** dùng để hiểu độ nhất quán giữa các judge sau khi trừ phần đồng thuận do ngẫu nhiên. Trong bài này hệ thống bucket điểm thành `excellent/good/partial/poor` rồi tính `cohens_kappa_bucketed = 0.4602`; đồng thời tính `weighted_cohens_kappa_ordinal = 0.5319` cho thang điểm ordinal 1-5. Kappa thấp hơn agreement rate vì agreement rate cho phép near-match theo tolerance, còn Kappa phạt phân phối nhãn và đồng thuận ngẫu nhiên. Vì vậy em dùng thêm `score_spread`, `conflict_cases` và conservative conflict resolution thay vì chỉ nhìn agreement rate.

**Position Bias** là hiện tượng judge thích câu trả lời A chỉ vì A xuất hiện trước B. Cách kiểm tra là đảo thứ tự response A/B và đo `bias_delta`; report hiện ghi `avg_bias_delta = 0.2326` trên 55 cases để chứng minh evaluator có bước calibration.

**Cost vs Quality Trade-off:** Judge mạnh hơn thường đắt hơn. Cách giảm cost 30% mà ít giảm chất lượng là cache case ổn định, dùng judge rẻ cho easy cases, chỉ gọi judge mạnh cho hard/adversarial hoặc conflict cases.

## 3. Problem Solving
Vấn đề lớn nhất là làm bài chạy được cả khi môi trường chấm không có API key, nhưng vẫn thể hiện kiến trúc production. Cách giải quyết là hỗ trợ deterministic offline judge, đồng thời giữ real API path cho OpenAI/Anthropic. Trong lần chạy cuối, Anthropic API bị chặn do billing nên hệ thống tự động dùng `gpt-4o-mini` + `gpt-4.1-mini` làm hai real model judges và ghi rõ `judge_mode_counts.real_api = 55`.

Một vấn đề khác là nếu chỉ báo `agreement_rate` thì chưa đủ thuyết phục cho rubric expert. Em đã bổ sung `judge_consensus` vào `reports/summary.json`, gồm danh sách judge, mode đang chạy, số conflict cases, average spread và Cohen's Kappa. Nhờ vậy grader có thể kiểm tra trực tiếp độ đồng thuận thay vì phải đọc code thủ công.

## 4. Kết quả
- V2 avg score: 4.3909 / 5.0
- V2 Hit Rate: 96.36%
- V2 MRR: 95.15%
- V2 Agreement Rate: 99.09%
- V2 Cohen's Kappa bucketed: 0.4602
- V2 Weighted Cohen's Kappa ordinal: 0.5319
- V2 Conflict Cases: 1/55
- V2 Red-team Pass Rate: 100%, trong khi red-team phá V1 ở `case_055_case_red_005`
- V2 Pass Rate: 100.00%
- V2 Wall-clock: 107.5373s cho 55 cases với real model judges, dưới ngưỡng 2 phút
- Release Gate: APPROVE_RELEASE
