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


def _score_bucket(score: float) -> str:
    if score >= 4.5:
        return "excellent"
    if score >= 3.5:
        return "good"
    if score >= 2.5:
        return "partial"
    return "poor"


def _cohens_kappa(labels_a: List[str], labels_b: List[str]) -> float:
    if not labels_a or len(labels_a) != len(labels_b):
        return 0.0

    total = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / total
    categories = sorted(set(labels_a) | set(labels_b))
    expected = 0.0
    for category in categories:
        prob_a = sum(1 for label in labels_a if label == category) / total
        prob_b = sum(1 for label in labels_b if label == category) / total
        expected += prob_a * prob_b
    if expected >= 1.0:
        return 1.0
    return round((observed - expected) / (1 - expected), 4)


def _weighted_cohens_kappa(scores_a: List[float], scores_b: List[float]) -> float:
    if not scores_a or len(scores_a) != len(scores_b):
        return 0.0

    categories = [1, 2, 3, 4, 5]
    rounded_pairs = [
        (min(5, max(1, round(a))), min(5, max(1, round(b))))
        for a, b in zip(scores_a, scores_b)
    ]
    total = len(rounded_pairs)
    hist_a = {category: sum(1 for a, _ in rounded_pairs if a == category) for category in categories}
    hist_b = {category: sum(1 for _, b in rounded_pairs if b == category) for category in categories}

    observed_weighted = 0.0
    expected_weighted = 0.0
    max_distance = (len(categories) - 1) ** 2
    for a in categories:
        for b in categories:
            weight = ((a - b) ** 2) / max_distance
            observed = sum(1 for x, y in rounded_pairs if x == a and y == b) / total
            expected = (hist_a[a] / total) * (hist_b[b] / total)
            observed_weighted += weight * observed
            expected_weighted += weight * expected

    if expected_weighted == 0:
        return 1.0 if observed_weighted == 0 else 0.0
    return round(1 - (observed_weighted / expected_weighted), 4)


def _judge_consensus_summary(results: List[Dict]) -> Dict:
    total = len(results) or 1
    judge_modes: Dict[str, int] = {}
    conflict_count = 0
    score_spreads = []
    labels_a: List[str] = []
    labels_b: List[str] = []
    scores_a: List[float] = []
    scores_b: List[float] = []
    judge_names = set()

    for item in results:
        judge = item["judge"]
        judge_modes[judge.get("judge_mode", "unknown")] = judge_modes.get(judge.get("judge_mode", "unknown"), 0) + 1
        if judge.get("requires_conflict_resolution"):
            conflict_count += 1
        score_spreads.append(judge.get("score_spread", 0.0))

        individual_scores = judge.get("individual_scores", {})
        judge_names.update(individual_scores.keys())
        if len(individual_scores) >= 2:
            scores = list(individual_scores.values())[:2]
            scores_a.append(scores[0])
            scores_b.append(scores[1])
            labels_a.append(_score_bucket(scores[0]))
            labels_b.append(_score_bucket(scores[1]))

    return {
        "configured_judges": sorted(judge_names),
        "judge_mode_counts": dict(sorted(judge_modes.items())),
        "judge_path_note": (
            "Preferred path is OpenAI + Anthropic. If Anthropic is unavailable, the engine uses "
            "gpt-4o-mini + gpt-4.1-mini so every case still has two real model-judge scores."
        ),
        "conflict_cases": conflict_count,
        "conflict_rate": round(conflict_count / total, 4),
        "avg_score_spread": round(sum(score_spreads) / total, 4),
        "cohens_kappa_bucketed": _cohens_kappa(labels_a, labels_b),
        "weighted_cohens_kappa_ordinal": _weighted_cohens_kappa(scores_a, scores_b),
        "kappa_bucket_definition": "Scores are bucketed as excellent/good/partial/poor before Cohen's Kappa.",
    }


def _position_bias_summary(results: List[Dict]) -> Dict:
    deltas = []
    for item in results:
        answer = item.get("agent_response", "")
        expected = item.get("expected_answer", "")
        if not answer or not expected:
            continue
        answer_tokens = set(answer.lower().split())
        expected_tokens = set(expected.lower().split())
        forward = len(answer_tokens & expected_tokens) / max(1, len(expected_tokens))
        swapped = len(answer_tokens & expected_tokens) / max(1, len(answer_tokens))
        deltas.append(abs(forward - swapped))

    if not deltas:
        return {"sample_size": 0, "avg_bias_delta": 0.0, "max_bias_delta": 0.0}
    return {
        "sample_size": len(deltas),
        "avg_bias_delta": round(sum(deltas) / len(deltas), 4),
        "max_bias_delta": round(max(deltas), 4),
        "method": "Lexical A/B swap proxy used for deterministic offline calibration.",
    }


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
    red_team_results = [item for item in results if item["metadata"]["case"].get("type") in {
        "prompt-injection",
        "goal-hijacking",
        "out-of-context",
        "ambiguous",
        "conflicting-assumption",
    }]
    red_team_total = len(red_team_results) or 1
    return {
        "metadata": {
            "version": agent_version,
            "total": len(results),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "batching": "asyncio.gather with bounded batches",
        },
        "metrics": metrics,
        "judge_consensus": _judge_consensus_summary(results),
        "position_bias": _position_bias_summary(results),
        "red_team": {
            "total": len(red_team_results),
            "pass_rate": round(sum(1 for item in red_team_results if item["status"] == "pass") / red_team_total, 4),
            "failure_cases": [item["case_id"] for item in red_team_results if item["status"] == "fail"],
            "case_types": sorted({item["metadata"]["case"].get("type") for item in red_team_results}),
        },
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
