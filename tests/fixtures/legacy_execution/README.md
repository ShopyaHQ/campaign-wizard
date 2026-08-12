# Legacy execution replay fixture (HISTORICAL / COMPATIBILITY ONLY)

Self-contained input for `tests/test_execution.py`, which exercises `scripts/build_csv.py
--legacy-replay` — a LEGACY builder retained only to reproduce historic Wizard-authored
CSV builds. This fixture reproduces the shape of the (now-deleted) Engine campaign-output
`collections/*/products.csv` files plus a matching `product_results_log.jsonl` for the
availability join.

NOT current production architecture. NOT loaded by any current production command. The
current contract hydrates all product facts from Engine truth via
`scripts/build_execution_csv.py`; this fixture and builder are historical only.
