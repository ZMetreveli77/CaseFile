simple-01: keep
The paragraph says exactly “opened on 31 May 1980”, and there’s only one Den Helder Zuid station. One thing to be aware of: if the agent answers “May 31, 1980”, exact match fails even though it’s right. Token F1 still gives 1.0, because the same three words appear in a different order. That’s a good example of why you report both metrics.

simple-02: fix (small)
The answer 6350 is in the paragraph, and if the model writes “6,350”, normalization removes the comma, so it still matches. But “Dhusha” is a fairly generic Nepali place name, so name the district to make it unambiguous:

What was the population of Dhusha, in Dhading District, at the time of the 1991 Nepal census? → 6350

The paragraph’s title is spelled “Dhussa” while the text says “Dhusha”. That’s fine for the answer, but keep it in mind if retrieval misses it.

simple-03: replace
Technically answerable, since the last sentence mentions Djoser. But it’s a bad simple question for two reasons:

It asks about the historical Imhotep, but its gold paragraph is about the film character “Imhotep (The Mummy)”. Search returned real pharaohs instead (Ahmose-ankh, Seqenenre Tao, Ahmose I), so retrieval counted it as a miss. (Correction, checked against the corpus: there is no separate “Imhotep” article in our corpus; the miss comes from the question not matching its paragraph.)
The answer is well-known general knowledge, so the model can answer from memory without searching, and the question tests nothing.

Ask about what the paragraph is actually about instead:

Who plays Ahmanet, the female version of Imhotep, in the 2017 remake of The Mummy? → Sofia Boutella

simple-04: keep
The answer is stated directly, and the title plus the year identify the film uniquely. The question copies the paragraph’s wording almost word for word, which makes it easy for keyword search. That’s acceptable for the “simple” category.

simple-05: fix (wording)
The answer matches the paragraph (“created by series creator Matt Groening”). “The animated television series character” is clumsy, so name the show:

Who created The Simpsons character Hans Moleman? → Matt Groening

simple-06: fix
You flagged the right problem. The paragraph says “Language has been the inspiration for both her writing and her art”. It doesn’t say “primary”, so the question claims something the source doesn’t. Use the paragraph’s own claim:

What has been the inspiration for both Roberta Allen’s writing and her art? → Language

There’s a remaining risk: the same paragraph also talks about “text”, so a model might answer “text” or “words” and score 0. If you’d rather avoid one-word abstract answers entirely, replace this question with one from a different paragraph.

simple-07: fix
The Cool and the Crazy (1958, directed by William Witney) is a different film, and normalize_answer even removes “the”, so the two titles look identical. That film is not in our corpus (checked), but the LLM may know it from training, so the question is ambiguous for the model. Add the year and the actors:

Who directed the 1994 film Cool and the Crazy, starring Jared Leto and Alicia Silverstone? → Ralph Bakshi

simple-08: fix
“Crossed” is the title of episodes of several shows. Name the series:

Who wrote “Crossed”, the fifth-season episode of The Walking Dead? → Seth Hoffman

simple-09: fix (the answer)
The question is clear, since “on CBS” rules out other works called The Nanny. But if the model answers “6” or “Six”, the gold “six seasons” gives exact match False, and against “6” token F1 is 0. Change the gold answer to “six”. That still misses “6”, which is a known weakness of word-based scoring (numbers written as digits vs words) and worth mentioning in your report.

simple-10: keep
“based in San Antonio, Texas” is stated directly. Corpus Christi appears too, but only as the site of the first restaurant, so the question isn’t ambiguous.


None of the unanswerable questions were answerable.