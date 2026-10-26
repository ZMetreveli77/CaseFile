# Reranker tuning (dev split, 20 questions; 1 question = 0.05)

Metric fixed before running: all_found@10, tie-breaker MRR (multi-hop needs both supporting paragraphs).

- **Winner:** coverage_weight 0.0, mmr_lambda 1.0 (dense_rank_limit 5/10/20 all tie): all_found@10 0.85, MRR 0.917.
- **Plain hybrid (no rerank):** all_found@10 0.80, MRR 0.867. **Current rerank (0.3 / 0.6 / 10):** 0.75, MRR 0.879 (rank 56 of 60).
- The winner beats plain hybrid by 0.05 = **one question**, which is within noise on 20 questions. The rule was
  "change rerank.py only if it wins by more than one question", so it doesn't qualify.
- The winner is also hybrid in disguise: coverage 0.0 means relevance = fused score only, and lambda 1.0 turns MMR off.
  What remains is the fused order plus the junk filter. So the extra reranker features never helped on dev.
- The current settings are one question *worse* than plain hybrid. Isolating the two features (dense_rank_limit 10):
  turning MMR on (lambda 0.6 vs 1.0, coverage 0.0) drops all_found@10 from 0.85 to 0.75 (two questions lose a needed
  paragraph to the diversity penalty); turning coverage on (0.3 vs 0.0, lambda 1.0) drops it from 0.85 to 0.80.
  (This did not affect the contradiction test: its retrieval check with hybrid_rerank found both sources 10/10.)
- **Decision:** make plain `hybrid` the default search mode. It is simpler, has fewer settings to justify, and is
  as good as anything in the grid. The reranker stays in the code as an option (`mode="hybrid_rerank"`).
- Confirm once on the test split; no further tuning after that.