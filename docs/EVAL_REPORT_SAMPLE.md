# ClaimLens evaluation report

Generated 2026-10-27T14:51:09.788156+00:00 on 600 **synthetic** cases (seed 4242). These numbers verify the pipeline; they do not measure real-world accuracy.

## Extraction (rule-based extractor)
The parser and the generator share a vocabulary of field labels and layouts, so near-perfect scores here are expected and say little about unseen real documents. Real scans go through Document Intelligence and the LLM extractor, which must be evaluated on hand-labelled real samples.

### Bill fields (exact match)
| metric | value |
|---|---|
| bill_number | 1.0 |
| hospital_name | 1.0 |
| patient_name | 1.0 |
| admission_date | 1.0 |
| discharge_date | 1.0 |
| diagnosis | 1.0 |
| procedure | 1.0 |
| total_claimed | 0.9833 |
| city | 1.0 |

### Line items
| metric | value |
|---|---|
| precision | 0.9977 |
| recall | 0.9801 |
| f1 | 0.9888 |

### Discharge summary fields
| metric | value |
|---|---|
| diagnosis | 1.0 |
| admission_date | 1.0 |
| discharge_date | 1.0 |
| history_of_condition_years | 1.0 |
| is_emergency | 1.0 |
| is_accident | 1.0 |

## Rule outcomes: extracted vs. true data
| metric | value |
|---|---|
| agreement | 0.9859 |
| false_pass_rate | 0.0 |
| became_unknown_rate | 0.01 |
| note | false_pass = rule fails on the true data but passes on the extracted data (the dangerous direction). |

## Anomaly detection (planted anomalies)
| anomaly | planted | recall | false-positive rate |
|---|---|---|---|
| inflate | 64 | 0.953 | 0.002 |
| duplicate | 27 | 1.0 | 0.0 |
| unbundle | 11 | 0.909 | 0.0 |
| days_over | 16 | 1.0 | 0.0 |

## Risk model (fresh seed)
Model `risk-a2db7e88-b782934c`

| metric | model | rules only |
|---|---|---|
| n | 600.0 | 600.0 |
| positive_rate | 0.3483 | 0.3483 |
| roc_auc | 0.8542 | 0.8208 |
| pr_auc | 0.7531 | 0.6892 |
| brier | 0.1437 | 0.2043 |
| ece | 0.0562 | 0.1983 |
| precision_at_20pct | 0.8083 | 0.7833 |

Ceiling AUC using the true generating probability: 0.8788

## Policy Q&A
| metric | value |
|---|---|
| in_scope_questions | 48 |
| hit_at_1 | 0.875 |
| hit_at_3 | 0.938 |
| wrongly_refused_in_scope | 0.062 |
| out_of_scope_questions | 10 |
| out_of_scope_refused | 1.0 |
| note | Questions were written by the same author as the retriever and the wording is generated from the same policy object, so treat these as optimistic. |

## Adversarial documents
| payload set | runs | flagged | failed check disappeared | extracted total changed |
|---|---|---|---|---|
| known phrasing | 60 | 1.0 | 0 | 0 |
| novel phrasing | 60 | 0.183 | 0 | 0 |

Detection is a heuristic tuned on the first list and will miss novel phrasing (second list). The safety property is structural: extraction has no tools, rules ignore free text, and nothing automated approves or rejects a claim.
