# Reflection - Nguyen Khanh Bang

## 1. Engineering Contribution
Em phụ trách hoàn thiện pipeline đánh giá end-to-end cho Lab Day 14:
- Thiết kế synthetic golden dataset 55 cases với `expected_retrieval_ids`, gồm grounded cases và red-team cases.
- Xây dựng RAG agent offline có retrieval theo corpus, trả `retrieved_ids`, contexts, token usage và estimated cost.
- Triển khai async benchmark runner để chạy nhiều cases song song theo batch.
- Tích hợp retrieval metrics gồm Hit Rate và MRR.
- Xây dựng multi-judge consensus gồm lexical accuracy judge và grounding/safety judge, có agreement rate và conflict resolution.
- Thêm regression release gate so sánh Agent V1 và Agent V2 bằng quality, retrieval, latency và cost.

## 2. Technical Depth
**Hit Rate** đo xem ít nhất một expected document có nằm trong top-k retrieval hay không. Metric này trả lời câu hỏi: "Retriever có lấy được bằng chứng đúng không?"

**MRR** đo vị trí của tài liệu đúng đầu tiên. Nếu tài liệu đúng đứng rank 1 thì MRR = 1.0; rank 2 thì 0.5. MRR quan trọng vì context đứng càng cao thì generator càng dễ dùng đúng bằng chứng.

**Cohen's Kappa / Agreement Thinking** dùng để hiểu độ nhất quán giữa các judge. Trong bài này hệ thống báo `agreement_rate` theo tolerance score vì judge là deterministic offline; nếu dùng judge người hoặc LLM thật, có thể mở rộng sang Cohen's Kappa để trừ phần đồng thuận do ngẫu nhiên.

**Position Bias** là hiện tượng judge thích câu trả lời A chỉ vì A xuất hiện trước B. Cách kiểm tra là đảo thứ tự response A/B và đo `bias_delta`.

**Cost vs Quality Trade-off:** Judge mạnh hơn thường đắt hơn. Cách giảm cost 30% mà ít giảm chất lượng là cache case ổn định, dùng judge rẻ cho easy cases, chỉ gọi judge mạnh cho hard/adversarial hoặc conflict cases.

## 3. Problem Solving
Vấn đề lớn nhất là làm bài chạy được trong môi trường không có API key nhưng vẫn thể hiện kiến trúc production. Cách giải quyết là dùng deterministic offline judge và agent, nhưng vẫn giữ đầy đủ interface của hệ thống thật: async runner, retrieval IDs, token/cost accounting, multi-judge consensus và release gate.

Một vấn đề khác là Windows console không in được emoji trong `check_lab.py`, gây lỗi `UnicodeEncodeError`. Em xử lý bằng cách đổi output checker sang ASCII text để script kiểm tra định dạng chạy ổn trên máy chấm.

## 4. Kết quả
- V2 avg score: 4.3504 / 5.0
- V2 Hit Rate: 96.36%
- V2 MRR: 95.15%
- V2 Agreement Rate: 85.91%
- V2 Pass Rate: 98.18%
- Release Gate: APPROVE_RELEASE
