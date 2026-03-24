#!/usr/bin/env python
"""Run a lightweight local benchmark for YinShield."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yinshield import Shield, ShieldSession


def load_dataset(path: Path) -> List[Dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(dataset: List[Dict[str, object]], mode: str, strategy: str) -> Dict[str, object]:
    shield = Shield(mode=mode, strategy=strategy)
    expected_total = 0
    matched_total = 0
    false_positive_total = 0
    recovery_total = 0
    semantic_proxy_sum = 0.0
    cases = []

    for item in dataset:
        text = str(item["text"])
        expected = item.get("expected", {})
        session = ShieldSession()
        masked, mapping = shield.mask(text, session=session)
        restored = shield.unmask(masked, mapping)
        expected_values = {
            value
            for values in dict(expected).values()
            for value in values
        }
        detected_values = set(mapping.values())

        case_matches = len(expected_values & detected_values)
        case_false_positives = len(detected_values - expected_values)
        expected_total += len(expected_values)
        matched_total += case_matches
        false_positive_total += case_false_positives
        recovery_total += int(restored == text)
        semantic_proxy = format_preservation(mapping)
        semantic_proxy_sum += semantic_proxy

        cases.append(
            {
                "id": item["id"],
                "masked_text": masked,
                "matches": case_matches,
                "expected": len(expected_values),
                "false_positives": case_false_positives,
                "recovery_ok": restored == text,
                "semantic_proxy": round(semantic_proxy, 3),
            }
        )

    precision = matched_total / max(1, matched_total + false_positive_total)
    recall = matched_total / max(1, expected_total)
    recovery_rate = recovery_total / max(1, len(dataset))
    average_semantic_proxy = semantic_proxy_sum / max(1, len(dataset))

    return {
        "mode": mode,
        "strategy": strategy,
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "false_positive_rate": round(false_positive_total / max(1, len(dataset)), 4),
            "recovery_rate": round(recovery_rate, 4),
            "semantic_proxy": round(average_semantic_proxy, 4),
        },
        "cases": cases,
    }


def format_preservation(mapping: Dict[str, str]) -> float:
    if not mapping:
        return 1.0

    scores = []
    for replacement, original in mapping.items():
        original_classes = summarize_char_classes(original)
        replacement_classes = summarize_char_classes(replacement)
        same_digit_shape = sum(char.isdigit() for char in original) == sum(char.isdigit() for char in replacement)
        scores.append(
            (
                int(original_classes == replacement_classes)
                + int(same_digit_shape)
                + int(abs(len(original) - len(replacement)) <= max(2, len(original) // 2))
            )
            / 3.0
        )
    return sum(scores) / len(scores)


def summarize_char_classes(value: str) -> str:
    parts = []
    for char in value:
        if "\u4e00" <= char <= "\u9fff":
            parts.append("C")
        elif char.isdigit():
            parts.append("D")
        elif char.isalpha():
            parts.append("A")
        else:
            parts.append("S")
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default="benchmarks/sample_dataset.json",
        help="Benchmark dataset path.",
    )
    parser.add_argument("--mode", choices=["placeholder", "alias"], default="placeholder")
    parser.add_argument("--strategy", choices=["loose", "balanced", "strict"], default="strict")
    parser.add_argument(
        "--output",
        default="benchmarks/sample_results.json",
        help="Where to write the benchmark report.",
    )
    args = parser.parse_args()

    dataset = load_dataset(Path(args.dataset))
    report = evaluate(dataset, mode=args.mode, strategy=args.strategy)
    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
