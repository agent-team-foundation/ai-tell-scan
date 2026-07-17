# AI Tell Scan precision report

Command:

```bash
python3 -B .claude/skills/ai-tell-scan/scripts/evaluate.py --output /tmp/ai-tell-scan-eval.json
```

Result on bundled `ats-gold-1` corpus v1.0.0:

| Metric | Result |
| --- | ---: |
| Projects | 30 |
| Positive projects | 15 |
| Hard-negative projects | 13 |
| Not-applicable projects | 2 |
| React / Next.js projects | 17 / 13 |
| Emitted-candidate TP / FP / FN | 23 / 0 / 0 |
| Candidate precision / recall | 1.0000 / 1.0000 |
| Blinded agent-confirmed TP / FP / FN | 20 / 0 / 0 |
| Confirmed precision | 1.0000 |
| Confirmed recall | 1.0000 |
| F1 | 1.0000 |
| Status mismatches | 0 |
| Framework mismatches | 0 |
| Invalid evidence locations | 0 |
| Review completeness problems | 0 |
| Blinded decisions / rejections | 23 / 3 |
| Always-confirm precision | 0.8696 (fails `>= 0.90`) |
| Precision gate | PASS (`>= 0.90`) |

## Per-rule result

| Rule | Candidate TP/FP/FN | Confirmed TP/FP/FN | Candidate precision | Confirmed precision |
| --- | ---: | ---: | ---: | ---: |
| `ats.aurora-centered-hero` | 2/0/0 | 2/0/0 | 1.0000 | 1.0000 |
| `ats.glass-card-field` | 2/0/0 | 2/0/0 | 1.0000 | 1.0000 |
| `ats.glass-floating-nav` | 2/0/0 | 2/0/0 | 1.0000 | 1.0000 |
| `ats.gradient-display-heading` | 3/0/0 | 2/0/0 | 1.0000 | 1.0000 |
| `ats.icon-card-triptych` | 2/0/0 | 2/0/0 | 1.0000 | 1.0000 |
| `ats.multicolor-card-wash` | 2/0/0 | 2/0/0 | 1.0000 | 1.0000 |
| `ats.pill-role-overload` | 2/0/0 | 2/0/0 | 1.0000 | 1.0000 |
| `ats.repeated-section-kickers` | 2/0/0 | 2/0/0 | 1.0000 | 1.0000 |
| `ats.round-metric-proof-row` | 3/0/0 | 2/0/0 | 1.0000 | 1.0000 |
| `ats.spring-hover-everywhere` | 3/0/0 | 2/0/0 | 1.0000 | 1.0000 |

The agent review artifact contains all 30 projects and 23 explicit decisions:
20 confirmations and 3 context-based rejections. The reviewer was not given
the gold manifest. Those rejection cases make an always-confirm policy score
0.8696 and fail the 0.90 gate. This result is still a controlled-corpus
regression gate. The projects are compact, fictional, de-identified, and
independently authored for this repository; the result does not establish
population-wide 100% precision. The real First Tree Web sample scanned 336
source files / 243 UI files and produced zero composite candidates; see
[`examples/first-tree-web/ats-1.json`](../../../../examples/first-tree-web/ats-1.json)
for the limitation-qualified report.
