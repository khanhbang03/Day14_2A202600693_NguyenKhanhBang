import asyncio
import json
import os
import time
from typing import Dict, List, Tuple

from agent.main_agent import MainAgent
from engine.llm_judge import LLMJudge
from engine.retrieval_eval import RetrievalEvaluator
from engine.runner import BenchmarkRunner


QUALITY_THRESHOLD = 3.6
HIT_RATE_THRESHOLD = 0.85
LATENCY_THRESHOLD_SECONDS = 2.0
COST_THRESHOLD_USD = 0.01


def _load_dataset(path: str = "data/golden_set.jsonl") -> List[Dict]:
    if not os.path.exists(path):
        raise FileNotFoundError("Thiếu data/golden_set.jsonl. Hãy chạy 'python data/synthetic_gen.py' trước.")
    with open(path, "r", encoding="utf-8") as f:
        dataset = [json.loads(line) for line in f if line.strip()]
    if len(dataset) < 50:
        raise ValueError(f"Golden dataset cần ít nhất 50 cases, hiện có {len(dataset)}.")
    return dataset


def _summarize(results: List[Dict], agent_version: str, elapsed: float) -> Dict:
    total = len(results) or 1
    pass_count = sum(1 for item in results if item["status"] == "pass")
    total_tokens = sum(item["metadata"]["agent"].get("tokens_used", 0) for item in results)
    total_cost = sum(item["metadata"]["agent"].get("estimated_cost_usd", 0.0) for item in results)
    metrics = {
        "avg_score": round(sum(item["judge"]["final_score"] for item in results) / total, 4),
        "pass_rate": round(pass_count / total, 4),
        "hit_rate": round(sum(item["ragas"]["retrieval"]["hit_rate"] for item in results) / total, 4),
        "mrr": round(sum(item["ragas"]["retrieval"]["mrr"] for item in results) / total, 4),
        "faithfulness": round(sum(item["ragas"]["faithfulness"] for item in results) / total, 4),
        "relevancy": round(sum(item["ragas"]["relevancy"] for item in results) / total, 4),
        "agreement_rate": round(sum(item["judge"]["agreement_rate"] for item in results) / total, 4),
        "avg_latency_seconds": round(sum(item["latency"] for item in results) / total, 4),
        "wall_clock_seconds": round(elapsed, 4),
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_cost, 8),
        "cost_per_case_usd": round(total_cost / total, 8),
    }
    return {
        "metadata": {
            "version": agent_version,
            "total": len(results),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "batching": "asyncio.gather with bounded batches",
        },
        "metrics": metrics,
    }


def _release_gate(v1: Dict, v2: Dict) -> Dict:
    v1_metrics = v1["metrics"]
    v2_metrics = v2["metrics"]
    deltas = {
        "avg_score": round(v2_metrics["avg_score"] - v1_metrics["avg_score"], 4),
        "hit_rate": round(v2_metrics["hit_rate"] - v1_metrics["hit_rate"], 4),
        "mrr": round(v2_metrics["mrr"] - v1_metrics["mrr"], 4),
        "cost": round(v2_metrics["estimated_cost_usd"] - v1_metrics["estimated_cost_usd"], 8),
        "latency": round(v2_metrics["avg_latency_seconds"] - v1_metrics["avg_latency_seconds"], 4),
    }
    checks = {
        "quality_non_regression": deltas["avg_score"] >= 0,
        "minimum_quality": v2_metrics["avg_score"] >= QUALITY_THRESHOLD,
        "retrieval_threshold": v2_metrics["hit_rate"] >= HIT_RATE_THRESHOLD,
        "latency_threshold": v2_metrics["avg_latency_seconds"] <= LATENCY_THRESHOLD_SECONDS,
        "cost_threshold": v2_metrics["estimated_cost_usd"] <= COST_THRESHOLD_USD,
    }
    decision = "APPROVE_RELEASE" if all(checks.values()) else "BLOCK_RELEASE"
    return {"decision": decision, "checks": checks, "deltas": deltas}


async def run_benchmark_with_results(agent_version: str, dataset: List[Dict]) -> Tuple[List[Dict], Dict]:
    print(f"Khoi dong benchmark cho {agent_version}...")
    runner = BenchmarkRunner(MainAgent(version=agent_version), RetrievalEvaluator(), LLMJudge())
    start = time.perf_counter()
    results = await runner.run_all(dataset, batch_size=10)
    elapsed = time.perf_counter() - start
    return results, _summarize(results, agent_version, elapsed)


async def main() -> None:
    try:
        dataset = _load_dataset()
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return

    v1_results, v1_summary = await run_benchmark_with_results("Agent_V1_Base", dataset)
    v2_results, v2_summary = await run_benchmark_with_results("Agent_V2_Optimized", dataset)
    gate = _release_gate(v1_summary, v2_summary)
    v2_summary["regression"] = {"baseline": v1_summary, "gate": gate}

    os.makedirs("reports", exist_ok=True)
    with open("reports/summary.json", "w", encoding="utf-8") as f:
        json.dump(v2_summary, f, ensure_ascii=False, indent=2)
    with open("reports/benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "v1_results": v1_results,
                "v2_results": v2_results,
                "regression_gate": gate,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\n--- KET QUA SO SANH REGRESSION ---")
    print(f"V1 Score: {v1_summary['metrics']['avg_score']}")
    print(f"V2 Score: {v2_summary['metrics']['avg_score']}")
    print(f"Delta Score: {gate['deltas']['avg_score']:+.4f}")
    print(f"Hit Rate V2: {v2_summary['metrics']['hit_rate']}")
    print(f"Agreement V2: {v2_summary['metrics']['agreement_rate']}")
    print(f"Cost V2: ${v2_summary['metrics']['estimated_cost_usd']:.8f}")
    print(f"QUYET DINH: {gate['decision']}")


if __name__ == "__main__":
    asyncio.run(main())
