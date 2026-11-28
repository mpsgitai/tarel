# Evaluations

Experiments and evaluations that need optional runtimes or private state, so they are not part of
the unit suite in `tests/`:

| File | Needs |
| --- | --- |
| `test_sqlite_vec_trial.py` | the `tarel[vector]` extra (sqlite-vec) |
| `test_qwen_runtime.py` | the `tarel[local-rag]` extra and a downloaded GGUF model |
| `test_retrieval_scopes.py` | `TAREL_EVAL_STATE` / `TAREL_EVAL_WORKSPACE` pointing at a real state |
| `check_agent_output_budgets.py` | `--state` pointing at the BI Lab `.tarel`; copied to a temporary directory, never written |

Run them from the repository root:

```bash
python -m unittest discover -s tools/evals -t . -q
```
