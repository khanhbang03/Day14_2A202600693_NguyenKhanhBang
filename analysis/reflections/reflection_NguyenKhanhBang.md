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

**MRR (Mean Reciprocal Rank)** đo chất lượng thứ hạng của retrieval, không chỉ đo việc có lấy được tài liệu đúng hay không. Với mỗi câu hỏi, hệ thống tìm vị trí của expected document đầu tiên trong danh sách retrieved docs, rồi tính `1 / rank`. Nếu tài liệu đúng ở rank 1 thì reciprocal rank = 1.0; rank 2 thì = 0.5; rank 3 thì = 0.333; nếu không tìm thấy thì = 0. MRR là trung bình các reciprocal rank trên toàn bộ dataset. Trong bài này V2 đạt `MRR = 95.15%`, nghĩa là phần lớn evidence đúng nằm rất gần đầu danh sách retrieval. Điều này quan trọng vì generator thường ưu tiên context đầu tiên; Hit Rate cao nhưng MRR thấp vẫn có thể khiến answer kém do tài liệu đúng bị chôn sau nhiều context nhiễu.

**Cohen's Kappa** đo mức độ đồng thuận giữa hai judge sau khi đã trừ đi phần đồng thuận có thể xảy ra do ngẫu nhiên. Nếu chỉ dùng agreement rate, hai judge có thể nhìn như đồng ý cao vì phần lớn case đều dễ hoặc đều nằm trong cùng một vùng điểm. Cohen's Kappa điều chỉnh điều này bằng ý tưởng: `Kappa = (observed agreement - expected random agreement) / (1 - expected random agreement)`. Kappa gần 1 nghĩa là đồng thuận mạnh; gần 0 nghĩa là đồng thuận không tốt hơn ngẫu nhiên nhiều; âm nghĩa là hai judge còn bất đồng có hệ thống. Trong bài này hệ thống bucket điểm thành `excellent/good/partial/poor` rồi tính `cohens_kappa_bucketed = 0.4602`; đồng thời tính `weighted_cohens_kappa_ordinal = 0.5319` cho thang điểm ordinal 1-5, vì lệch 4-vs-5 nhẹ hơn lệch 1-vs-5. Kappa thấp hơn agreement rate 99.09% vì agreement rate cho phép near-match theo tolerance, còn Kappa phạt phân phối nhãn và đồng thuận ngẫu nhiên. Vì vậy em không chỉ nhìn agreement rate, mà còn theo dõi `score_spread`, `conflict_cases` và dùng conservative conflict resolution khi hai judge lệch nhiều.

**Position Bias** là thiên lệch vị trí khi judge ưu tiên câu trả lời xuất hiện trước, ví dụ thích Answer A hơn Answer B chỉ vì A được đặt ở đầu prompt, không phải vì A thật sự tốt hơn. Bias này nguy hiểm trong evaluation vì nó làm kết quả ranking hoặc A/B test bị lệch dù nội dung hai câu trả lời tương đương. Cách kiểm tra là chấm cùng một cặp câu trả lời hai lần: lần đầu theo thứ tự A/B, lần sau đảo thành B/A, rồi đo độ lệch điểm (`bias_delta`). Nếu điểm thay đổi mạnh sau khi đảo vị trí thì evaluator có position bias cao. Trong bài này report ghi `avg_bias_delta = 0.2326` trên 55 cases như một bước calibration, giúp em biết judge có ổn định tương đối khi thứ tự presentation thay đổi hay không.

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
