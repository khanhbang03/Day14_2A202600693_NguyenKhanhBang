import json
import os
import sys


def configure_utf8_output():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def validate_lab():
    configure_utf8_output()
    print("🔍 Đang kiểm tra định dạng bài nộp...")

    required_files = [
        "reports/summary.json",
        "reports/benchmark_results.json",
        "analysis/failure_analysis.md"
    ]

    # 1. Kiểm tra sự tồn tại của tất cả file
    missing = []
    for f in required_files:
        if os.path.exists(f):
            print(f"✅ Tìm thấy: {f}")
        else:
            print(f"❌ Thiếu file: {f}")
            missing.append(f)

    if missing:
        print(f"\n❌ Thiếu {len(missing)} file. Hãy bổ sung trước khi nộp bài.")
        return

    # 2. Kiểm tra nội dung summary.json
    try:
        with open("reports/summary.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ File reports/summary.json không phải JSON hợp lệ: {e}")
        return

    if "metrics" not in data or "metadata" not in data:
        print("❌ File summary.json thiếu trường 'metrics' hoặc 'metadata'.")
        return

    metrics = data["metrics"]

    print(f"\n--- Thống kê nhanh ---")
    print(f"Tổng số cases: {data['metadata'].get('total', 'N/A')}")
    print(f"Điểm trung bình: {metrics.get('avg_score', 0):.2f}")

    # EXPERT CHECKS
    has_retrieval = "hit_rate" in metrics
    if has_retrieval:
        print(f"✅ Đã tìm thấy Retrieval Metrics (Hit Rate: {metrics['hit_rate']*100:.1f}%)")
    else:
        print(f"⚠️ CẢNH BÁO: Thiếu Retrieval Metrics (hit_rate).")

    has_multi_judge = "agreement_rate" in metrics
    if has_multi_judge:
        print(f"✅ Đã tìm thấy Multi-Judge Metrics (Agreement Rate: {metrics['agreement_rate']*100:.1f}%)")
    else:
        print(f"⚠️ CẢNH BÁO: Thiếu Multi-Judge Metrics (agreement_rate).")

    consensus = data.get("judge_consensus", {})
    if consensus.get("configured_judges") and "cohens_kappa_bucketed" in consensus:
        print(
            "✅ Đã tìm thấy Consensus Audit "
            f"(Judges: {', '.join(consensus['configured_judges'])}; "
            f"Kappa: {consensus['cohens_kappa_bucketed']:.4f}; "
            f"Weighted Kappa: {consensus.get('weighted_cohens_kappa_ordinal', 0):.4f})"
        )
    else:
        print("⚠️ CẢNH BÁO: Thiếu Consensus Audit hoặc Cohen's Kappa.")

    if data.get("position_bias", {}).get("sample_size", 0) >= 50:
        print(
            "✅ Đã tìm thấy Position Bias Calibration "
            f"(avg delta: {data['position_bias'].get('avg_bias_delta', 0):.4f})"
        )
    else:
        print("⚠️ CẢNH BÁO: Thiếu Position Bias Calibration cho >= 50 cases.")

    if data.get("red_team", {}).get("total", 0) >= 5:
        print(
            "✅ Đã tìm thấy Red Team Audit "
            f"({data['red_team']['total']} cases, pass rate: {data['red_team'].get('pass_rate', 0)*100:.1f}%)"
        )
    else:
        print("⚠️ CẢNH BÁO: Thiếu Red Team Audit.")

    if data["metadata"].get("version"):
        print(f"✅ Đã tìm thấy thông tin phiên bản Agent (Regression Mode)")

    if data.get("regression", {}).get("gate", {}).get("decision"):
        print(f"✅ Release Gate: {data['regression']['gate']['decision']}")
    else:
        print("⚠️ CẢNH BÁO: Thiếu Regression Release Gate.")

    print("\n🚀 Bài lab đã sẵn sàng để chấm điểm!")

if __name__ == "__main__":
    validate_lab()
