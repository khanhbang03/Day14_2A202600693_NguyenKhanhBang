import re
from typing import Dict, List


def _tokens(text: str) -> List[str]:
    return re.findall(r"[\wÀ-ỹ]+", text.lower())


class RetrievalEvaluator:
    def calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str], top_k: int = 3) -> float:
        top_retrieved = retrieved_ids[:top_k]
        return 1.0 if any(doc_id in top_retrieved for doc_id in expected_ids) else 0.0

    def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_ids:
                return 1.0 / (i + 1)
        return 0.0

    def _overlap_score(self, expected_answer: str, answer: str) -> float:
        expected = set(_tokens(expected_answer))
        actual = set(_tokens(answer))
        if not expected:
            return 0.0
        return min(1.0, len(expected & actual) / max(8, len(expected) * 0.45))

    async def score(self, case: Dict, response: Dict) -> Dict:
        expected_ids = case.get("expected_retrieval_ids", [])
        retrieved_ids = response.get("retrieved_ids", [])
        contexts = " ".join(response.get("contexts", []))
        answer = response.get("answer", "")

        hit_rate = self.calculate_hit_rate(expected_ids, retrieved_ids, top_k=3)
        mrr = self.calculate_mrr(expected_ids, retrieved_ids)
        answer_overlap = self._overlap_score(case.get("expected_answer", ""), answer)
        context_support = self._overlap_score(answer, contexts) if contexts else 0.0

        if case.get("metadata", {}).get("type") == "out-of-context" and "không" in answer.lower():
            context_support = max(context_support, 0.85)
            answer_overlap = max(answer_overlap, 0.8)

        return {
            "faithfulness": round((0.65 * context_support) + (0.35 * hit_rate), 4),
            "relevancy": round(answer_overlap, 4),
            "retrieval": {
                "hit_rate": hit_rate,
                "mrr": round(mrr, 4),
                "expected_ids": expected_ids,
                "retrieved_ids": retrieved_ids,
            },
        }

    async def evaluate_batch(self, dataset: List[Dict], responses: List[Dict]) -> Dict:
        scores = [await self.score(case, response) for case, response in zip(dataset, responses)]
        total = len(scores) or 1
        return {
            "avg_hit_rate": sum(item["retrieval"]["hit_rate"] for item in scores) / total,
            "avg_mrr": sum(item["retrieval"]["mrr"] for item in scores) / total,
            "avg_faithfulness": sum(item["faithfulness"] for item in scores) / total,
            "avg_relevancy": sum(item["relevancy"] for item in scores) / total,
        }
