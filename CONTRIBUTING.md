# Contributing

AI Tell Scan is intentionally precision-first. Before changing a rule, read the
signal and gold-set references in `.claude/skills/ai-tell-scan/references/`.

Every rule change must:

1. add or update at least one positive and one hard-negative corpus case;
2. keep candidate and context-confirmed precision at or above 0.90;
3. preserve valid file/line evidence and framework/status classification;
4. include a context-review rejection path when the candidate can be intentional;
5. pass the scanner tests, renderer tests, evaluator, and skill validator.

Run the commands in [README.md](README.md#development) before opening a pull
request. Keep target repository data out of commits unless it is fictional,
de-identified, and explicitly part of the controlled corpus.
