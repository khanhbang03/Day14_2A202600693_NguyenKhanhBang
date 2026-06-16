# Báo cáo Phân tích Thất bại (Failure Analysis Report)

## 1. Tổng quan Benchmark
- **Tổng số cases:** 55
- **Tỉ lệ Pass/Fail:** 55/0, pass rate 100.00%
- **Điểm LLM-Judge trung bình:** 4.3909 / 5.0
- **Retrieval:** Hit Rate 96.36%, MRR 95.15%
- **RAGAS-style:** Faithfulness 95.90%, Relevancy 97.82%
- **Multi-Judge:** Agreement Rate 99.09%, chạy real API với `gpt-4o-mini` và `gpt-4.1-mini`. Claude adapter cũng có sẵn, nhưng lần chạy này dùng OpenAI fallback vì Anthropic billing không khả dụng.
- **Consensus audit:** 1/55 cases cần conflict resolution, average score spread 0.3273, Cohen's Kappa bucketed = 0.4602, weighted ordinal Kappa = 0.5319.
- **Position Bias:** deterministic A/B swap proxy trên 55 cases, average bias delta 0.2326, max bias delta 0.4462.
- **Red Teaming:** 5 hard/adversarial cases gồm prompt injection, goal hijacking, out-of-context, ambiguous và conflicting assumption; bộ red-team phá vỡ V1 ở `case_055_case_red_005`, còn V2 pass 5/5 sau tối ưu.
- **Performance:** Async benchmark chạy 55 cases trong 107.5373s wall-clock khi gọi real model judges, latency agent trung bình 0.0294s/case, đạt yêu cầu < 2 phút.
- **Cost:** 5,470 tokens, ước tính 0.00098460 USD, tức khoảng 0.0000179 USD/case
- **Regression Gate:** APPROVE_RELEASE. V2 tăng +2.6091 điểm so với V1, hit rate tăng +1.81%, latency giảm 0.0230s/case.

## 2. Liên hệ Retrieval Quality và Answer Quality
Retrieval là tầng quyết định agent có đủ bằng chứng để trả lời hay không. Khi `hit_rate` và `mrr` cao, expected document thường xuất hiện trong top results và ở vị trí đầu, giúp answer có nhiều token trùng với ground truth hơn. Trong benchmark này, V2 có Hit Rate 96.36% và MRR 95.15%, kéo faithfulness lên 95.90% và pass rate lên 100%. Các điểm yếu còn lại nằm ở truy vấn mơ hồ hoặc giả định sai, nơi vấn đề không chỉ là lấy đúng tài liệu mà còn là policy trả lời: hỏi lại, từ chối hallucination, hoặc giải thích điều kiện.

## 3. Phân nhóm lỗi (Failure Clustering)
| Nhóm lỗi | Số lượng | Dấu hiệu | Nguyên nhân dự kiến |
|----------|----------|----------|---------------------|
| Ambiguous Query | 1 | Agent xử lý bằng câu hỏi làm rõ nhưng retrieval không lấy được `doc_red_team` | Query thiếu chủ thể như "nó", cần clarify slot và retrieval fallback |
| Retrieval Miss / Low Rank | 2 | Expected ID không nằm top-3 hoặc rơi xuống rank thấp | Lexical scorer chưa có synonym expansion |
| Judge Disagreement | 1 | Hai judge lệch hơn 1 điểm nhưng vẫn được hòa giải bằng conservative average | Real judges có rubric khác nhau ở case mơ hồ/không đầy đủ |
| Hard Prompt Safety | 0 critical | Prompt injection được chặn | Rule-based safe behavior hoạt động ổn |
| Cost/Latency Risk | 0 | Không vượt ngưỡng | Async batch giữ real-model benchmark dưới 2 phút |
| Red-Team Break | 1 trên V1, 0 trên V2 | Conflicting-assumption case phá baseline nhưng được V2 cải thiện đủ để pass | Regression loop đã giảm lỗi nhưng vẫn cần reranker/contradiction handling |

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

### Case #4: Red-team conflicting assumption phá vỡ baseline
1. **Symptom:** `case_055_case_red_005` phá V1 nhưng V2 đã pass dưới real multi-judge.
2. **Why 1:** Baseline trả lời quá chung và không bác bỏ giả định "lỗi chắc chắn do judge sai".
3. **Why 2:** V1 generator chỉ nói cần kiểm tra thêm, thiếu evidence cụ thể từ retrieval/failure-analysis docs.
4. **Why 3:** Retrieval có thể lấy evidence đúng nhưng generation policy chưa buộc phải phản biện assumption sai.
5. **Why 4:** Bộ test hard yêu cầu kết hợp retrieval metrics, faithfulness, relevancy và prompting trước khi kết luận judge sai.
6. **Root Cause:** Baseline thiếu contradiction handling; V2 cải thiện bằng grounded response, nhưng roadmap vẫn cần reranker ưu tiên evidence phản biện giả định.

## 5. Regression Gate
Gate tự động dùng 5 điều kiện:
- Quality không regression so với V1.
- Avg score V2 >= 3.6.
- Hit Rate V2 >= 0.85.
- Latency trung bình <= 2.0s.
- Tổng cost <= 0.01 USD.

Kết quả V2 đạt cả 5 điều kiện, nên quyết định là **APPROVE_RELEASE**.

## 6. Báo cáo Cost & Token Usage

### 6.1. Tổng quan chi phí
| Phiên bản | Cases | Prompt tokens | Completion tokens | Total tokens | Estimated cost | Cost/case | Avg tokens/case |
|----------|------:|--------------:|------------------:|-------------:|---------------:|----------:|----------------:|
| V1 Baseline | 55 | 2,326 | 1,076 | 3,402 | $0.00085050 | $0.00001546 | 61.85 |
| V2 Optimized | 55 | 2,996 | 2,474 | 5,470 | $0.00098460 | $0.00001790 | 99.45 |

V2 dùng nhiều hơn **2,068 tokens** so với V1, tương đương tăng **60.79% token volume**. Tuy nhiên cost chỉ tăng **$0.00013410** vì V2 dùng unit price thấp hơn trong metadata agent (`$0.00018/1K tokens` so với `$0.00025/1K tokens` của V1). Đổi lại, V2 tăng avg score từ **1.7818** lên **4.3909** và pass rate từ **7.27%** lên **100.00%**.

### 6.2. Phân rã token V2
| Thành phần | Tokens | Tỉ lệ |
|-----------|-------:|------:|
| Prompt/context tokens | 2,996 | 54.77% |
| Completion/answer tokens | 2,474 | 45.23% |
| Tổng | 5,470 | 100.00% |

Token tăng chủ yếu do V2 trả lời đầy đủ hơn và đưa thêm context liên quan vào answer. Đây là trade-off có lợi trong benchmark này: chi phí tăng nhẹ nhưng chất lượng tăng mạnh, retrieval giữ ổn định, và release gate vẫn đạt cost threshold.

### 6.3. Biên chi phí theo case
| Phiên bản | Min tokens/case | Max tokens/case | Min cost/case | Max cost/case |
|----------|----------------:|----------------:|--------------:|--------------:|
| V1 Baseline | 20 | 81 | $0.00000500 | $0.00002025 |
| V2 Optimized | 20 | 144 | $0.00000360 | $0.00002592 |

Các case có chi phí cao nhất thường là câu hỏi grounded/hard cần nhiều retrieved context. Các case out-of-context hoặc ambiguous có token thấp vì agent trả lời ngắn và không kéo nhiều tài liệu.

### 6.4. Red-team cost
| Phiên bản | Red-team cases | Red-team tokens | Red-team cost | Avg red-team cost/case |
|----------|---------------:|----------------:|--------------:|-----------------------:|
| V1 Baseline | 5 | 238 | $0.00005950 | $0.00001190 |
| V2 Optimized | 5 | 301 | $0.00005418 | $0.00001084 |

Dù V2 dùng nhiều token hơn trên red-team cases, cost red-team lại thấp hơn V1 do unit price thấp hơn. V2 cũng đạt **5/5 red-team pass**, trong khi V1 bị phá ở `case_055_case_red_005`.

### 6.5. ROI chất lượng trên chi phí
- Delta cost V2 - V1: **+$0.00013410**.
- Delta avg score V2 - V1: **+2.6091**.
- Chi phí tăng cho mỗi 1 điểm avg score cải thiện: khoảng **$0.00005140**.
- Cost threshold của release gate: **$0.01000000**.
- Actual V2 cost: **$0.00098460**, chỉ dùng khoảng **9.85%** budget.

Kết luận: V2 là lựa chọn hợp lý để release vì tăng mạnh quality với cost tăng rất nhỏ và vẫn thấp hơn nhiều so với ngân sách cho phép.

### 6.6. Kế hoạch giảm ít nhất 30% chi phí eval
1. **Cache judge results cho stable cases:** Các case synthetic-grounded lặp cấu trúc cao, có thể cache theo hash của question + answer + expected answer. Dự kiến giảm 25-40% judge calls khi rerun regression.
2. **Tiered judging:** Dùng một judge rẻ cho easy cases; chỉ gọi judge thứ hai khi score nằm vùng biên hoặc `score_spread > 1.0`. Với run hiện tại chỉ 1/55 cases cần conflict resolution, strategy này có thể giảm mạnh calls thứ hai.
3. **Context compaction:** Giới hạn answer builder chỉ đưa context thật cần thiết thay vì ghép nhiều document. Mục tiêu giảm 15-25% completion tokens ở các grounded cases dài.
4. **Sample stable regression cases:** Luôn chạy 100% red-team/hard cases, nhưng sample 50-70% easy/definition cases trong smoke regression. Full benchmark vẫn chạy trước release chính thức.
5. **Token budget guardrail:** Cảnh báo khi `tokens_used > 120` hoặc `cost_per_case > $0.000025`, vì đây là nhóm case dễ gây phình chi phí.

## 7. Kế hoạch cải tiến
- Thêm hybrid retrieval: lexical scorer hiện tại + vector embedding để tăng recall cho synonym và paraphrase.
- Thêm reranking theo cross-encoder hoặc LLM-small judge cho top-5 context.
- Chuẩn hóa prompt trả lời ambiguity: luôn hỏi rõ metric/version/dataset/pipeline trước khi kết luận.
- Thêm cache cho judge trên các case ổn định để giảm ít nhất 30% cost eval.
- Chạy position-bias calibration bằng cách đảo thứ tự answer A/B cho sample conflict cases.
- Lưu failure clusters tự động vào report để analyst không phải phân loại thủ công.
