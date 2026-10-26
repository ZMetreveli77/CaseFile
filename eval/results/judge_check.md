# LLM judge check (task E2)

> **Who checked:** Claude Code (an AI), at the author's request. This is **not** a human validation. A model checking
> another model is a weaker check: both can share the same blind spots. A human check on the same sample would make
> this stronger.

**Sample.** Answers to answerable questions (bridge, comparison, simple) with a judge verdict, from the first test
run (`answers_test_hybrid_first_run.json`, agent and baseline) and the latest dev run (`answers_dev_hybrid.json`):
50 judged answers.
- Where an answer exactly matches the gold answer, the judge has little to decide, so the check focuses on the
  **17 answers that are not exact matches**, where the judge's decision matters.
- 3 questions appear twice, answered by both configurations, so there are 14 distinct judgments.

| # | Question (short) | Gold | Predicted | Judge | Check |
|---|---|---|---|---|---|
| 1 | Company with a 10-year contract with the Escape From New York anti-hero | contract with The Walt Disney Company | The Walt Disney Company | ✓ | ✓ agree |
| 2 | French ace who flew L'Oiseau Blanc | Charles Eugène | Charles Nungesser | ✓ | ✓ agree (gold is a truncated full name: Charles Eugène Jules Marie Nungesser) |
| 3 | City where the PISCES developer is headquartered | McLean, Virginia | McLean | ✓ | ✓ agree |
| 4 | Are Lummerstorfer and Sarmiento both authors? | no | yes | ✗ | ✓ agree |
| 5 | Seasons of The Nanny on CBS | six | 6 | ✓ | ✓ agree (exact match fails on digits vs words) |
| 6 | (as 1, baseline) | | | ✓ | ✓ agree |
| 7 | What Tottenham Hotspur is commonly called | Spurs | Tottenham or Spurs | ✓ | ✓ agree (lenient: two names given) |
| 8 | (as 2, baseline) | | | ✓ | ✓ agree |
| 9 | (as 4, baseline) | | | ✗ | ✓ agree |
| 10 | Published most recently: Pirate's Cove or Catan? | Pirate's Cove | Catan | ✗ | ✓ agree |
| 11 | Born first: Todd Field or Aaron Katz? | William Todd Field | Todd Field | ✓ | ✓ agree |
| 12 | County Cari Roccaro is from | Suffolk | Suffolk County | ✓ | ✓ agree |
| 13 | Where Mike Leach coaches now | Washington State | Washington State Cougars | ✓ | ✓ agree |
| 14 | What kind of band released the ninth Desert Sessions LP | rock band | American desert rock collective | ✓ | ✓ agree (lenient but reasonable) |
| 15 | Trio of the songwriter of "What Are We Doin' Lonesome" | trio with his younger brothers Steve and Rudy | Larry Gatlin & the Gatlin Brothers | ✓ | ✓ agree |
| 16 | Creators of the sitcom with "Cartman Finds Love" | Trey Parker and Matt Stone | Matt Stone and Trey Parker | ✓ | ✓ agree |
| 17 | What Havelock Ellis and Arnold Bennett both were | writer | English writer | ✓ | ✓ agree |

## Result
- **Agreement 17/17** on the non-exact answers.
- Across all 50 judged answers, **no exact match was marked wrong** by the judge.
- The judge never accepted a factually wrong answer in this sample.

## Observations
- **The judge is slightly lenient** on answers that add detail or give two names (rows 7, 14). That matches its
  instructions ("extra correct detail is fine") but could hide over-long answers.
- **The judge fixes real scoring weaknesses:** digits vs words (row 5), extra qualifiers (rows 12, 13), word order
  (row 16) and **noisy gold answers** (rows 1, 2, 15: HotpotQA's gold strings are sometimes truncated or phrased
  oddly). This is why judge accuracy is reported next to exact match and F1.
- **Limits:**
  - The sample is small and mostly correct answers: only 3 of 14 distinct judgments are "incorrect".
  - The checker is an AI.
  - The judge was never tested on borderline wrong answers that look plausible.
