# Benchmarks

`run_benchmark.py` measures the current local MVP on a small labeled Chinese dataset.

Included metrics:
- `precision`
- `recall`
- `false_positive_rate`
- `recovery_rate`
- `semantic_proxy`

`semantic_proxy` is a local format-preservation heuristic. It is not a substitute for downstream LLM task evaluation.
