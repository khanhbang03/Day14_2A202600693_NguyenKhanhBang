# Báo cáo Phân tích Thất bại (Failure Analysis Report)

## 1. Tổng quan Benchmark
- **Tổng số cases:** 55
- **Tỉ lệ Pass/Fail:** 54/1, pass rate 98.18%
- **Điểm LLM-Judge trung bình:** 4.3504 / 5.0
- **Retrieval:** Hit Rate 96.36%, MRR 95.15%
- **RAGAS-style:** Faithfulness 95.90%, Relevancy 97.82%
- **Multi-Judge:** Agreement Rate 85.91%, gồm lexical accuracy judge và grounding/safety judge
- **Performance:** Async benchmark chạy 55 cases trong 0.1954s, latency trung bình 0.0298s/case
- **Cost:** 5,470 tokens, ước tính 0.00098460 USD, tức khoảng 0.0000179 USD/case
- **Regression Gate:** APPROVE_RELEASE. V2 tăng +1.9075 điểm so với V1, hit rate tăng +1.81%, latency giảm 0.0219s/case.

## 2. Liên hệ Retrieval Quality và Answer Quality
Retrieval là tầng quyết định agent có đủ bằng chứng để trả lời hay không. Khi `hit_rate` và `mrr` cao, expected document thường xuất hiện trong top results và ở vị trí đầu, giúp answer có nhiều token trùng với ground truth hơn. Trong benchmark này, V2 có Hit Rate 96.36% và MRR 95.15%, kéo faithfulness lên 95.90%. Các case fail còn lại chủ yếu nằm ở truy vấn mơ hồ hoặc giả định sai, nơi vấn đề không chỉ là lấy đúng tài liệu mà còn là policy trả lời: hỏi lại, từ chối hallucination, hoặc giải thích điều kiện.

## 3. Phân nhóm lỗi (Failure Clustering)
| Nhóm lỗi | Số lượng | Dấu hiệu | Nguyên nhân dự kiến |
|----------|----------|----------|---------------------|
| Ambiguous Query | 1 | Agent trả lời quá chung hoặc hỏi lại chưa đủ cụ thể | Query thiếu chủ thể như "nó", cần clarify slot |
| Retrieval Miss / Low Rank | 2 | Expected ID không nằm top-3 hoặc rơi xuống rank thấp | Lexical scorer chưa có synonym expansion |
| Judge Disagreement | 8 | Hai judge lệch hơn 1 điểm nhưng vẫn được hòa giải | Accuracy judge ưu tiên overlap, grounding judge phạt token ngoài ground truth |
| Hard Prompt Safety | 0 critical | Prompt injection được chặn | Rule-based safe behavior hoạt động ổn |
| Cost/Latency Risk | 0 | Không vượt ngưỡng | Async batch và offline deterministic judge đủ nhanh |

## 4. Phân tích 5 Whys

### Case #1: Câu hỏi mơ hồ "Nó có tốt không?"
1. **Symptom:** Agent phải hỏi rõ nhưng câu trả lời vẫn chưa chỉ ra đầy đủ các lựa chọn cần làm rõ.
2. **Why 1:** Query không chứa entity hoặc metric cụ thể.
3. **Why 2:** Retriever vẫn kéo `doc_red_team` nhưng generator chỉ có rule đơn giản cho ambiguity.
4. **Why 3:** Prompt/generation policy chưa có template hỏi lại theo slot: metric, version, dataset, hoặc pipeline.
5. **Why 4:** Bộ test hiện đo đúng/sai bằng expected answer, chưa chấm cao hơn cho câu hỏi follow-up có cấu trúc.
6. **Root Cause:** Prompting policy cho ambiguous requests còn nông, cần clarify template và evaluator cho multi-turn.

### Case #2: Retrieval miss ở hard/adversarial cases
1. **Symptom:** Một số câu hỏi có expected IDs kép nhưng retrieved top-k chỉ lấy được một ID.
2. **Why 1:** Lexical scorer ưu tiên title overlap và token match trực tiếp.
3. **Why 2:** Query dùng cách diễn đạt gián tiếp như "đạt điểm tối đa" hoặc "lỗi chắc chắn do judge sai".
4. **Why 3:** Corpus chưa có embedding semantic hoặc synonym mapping.
5. **Why 4:** Không có reranker kiểm tra expected evidence theo type hard/adversarial.
6. **Root Cause:** Retrieval hiện là BM25-like tối giản; cần semantic retrieval hoặc hybrid lexical + vector + reranker.

### Case #3: Judge disagreement
1. **Symptom:** Agreement không đạt 100% dù answer đúng phần lớn.
2. **Why 1:** Lexical accuracy judge chấm dựa trên overlap với ground truth.
3. **Why 2:** Grounding/safety judge chấm dựa trên mức độ token nằm trong expected answer.
4. **Why 3:** Answer có câu dẫn như "Dựa trên context truy xuất được", tạo token không xuất hiện trong expected answer.
5. **Why 4:** Rubric chưa tách phần style/tone khỏi phần factual support.
6. **Root Cause:** Calibration giữa hai judge cần thêm normalization và examples để phân biệt wording khác với lỗi factual.

## 5. Regression Gate
Gate tự động dùng 5 điều kiện:
- Quality không regression so với V1.
- Avg score V2 >= 3.6.
- Hit Rate V2 >= 0.85.
- Latency trung bình <= 2.0s.
- Tổng cost <= 0.01 USD.

Kết quả V2 đạt cả 5 điều kiện, nên quyết định là **APPROVE_RELEASE**.

## 6. Kế hoạch cải tiến
- Thêm hybrid retrieval: lexical scorer hiện tại + vector embedding để tăng recall cho synonym và paraphrase.
- Thêm reranking theo cross-encoder hoặc LLM-small judge cho top-5 context.
- Chuẩn hóa prompt trả lời ambiguity: luôn hỏi rõ metric/version/dataset/pipeline trước khi kết luận.
- Thêm cache cho judge trên các case ổn định để giảm ít nhất 30% cost eval.
- Chạy position-bias calibration bằng cách đảo thứ tự answer A/B cho sample conflict cases.
- Lưu failure clusters tự động vào report để analyst không phải phân loại thủ công.
