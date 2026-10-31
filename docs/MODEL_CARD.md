# Model card: ClaimLens query-risk model

## Read this first

**The model has only ever seen synthetic data.** The numbers below describe how well it recovers a *simulated* process that this repository's authors wrote. They demonstrate that the training, calibration, gating and serving pipeline works end to end. They are **not** evidence of accuracy on real Indian health-insurance claims, and must not be quoted as such.

## What it does

Estimates the probability that a claim will be **queried or reduced** by a reviewer, given the policy, the extracted bill and discharge summary, rule outcomes and billing anomalies. Output: a calibrated probability, a band (low < 25%, medium, high ≥ 60%) and up to three plain-language reasons from per-claim TreeSHAP contributions.

## Intended use

- Ordering a reviewer's queue so likely-problem claims are read first.
- Telling a reviewer *why* a claim looks risky, with the underlying rule results and anomaly evidence one click away.

## Not intended for

- Approving, rejecting, or reducing any claim. There is no such path in the product.
- Judging fraud, medical necessity or a patient's credibility.
- Use on any population, insurer or document format the model was not validated on. That includes every real one today.

## Model

- LightGBM gradient-boosted trees, binary objective, with **monotone-increasing** constraints on 11 features where the direction is not in doubt (failed blocker and warning rules, unverifiable checks, missing documents, duplicate lines, unbundling, days beyond stay, price outliers, hospital history, suspicious document text).
- Isotonic calibration fitted on a held-out calibration split; stored as JSON and applied with linear interpolation.
- Features (32): rule outcome counts, missing documents, price z-scores, anomaly counts, claim-level Isolation Forest percentile, hospital historical query rate, room rate relative to the cap, claim relative to sum insured, policy age, waiting-period proximity, stated condition length, extraction confidence, injection-flag count, and size/cost-per-day terms. The list is in `ml/features.py`.
- Hospital query rate uses **leave-one-out** on training rows so a row's own label never leaks into its feature. It is computed from the training split only.
- Splits: 60% train, 10% validation (early stopping), 15% calibration, 15% test. Default dataset: 5,000 synthetic cases, seed 42.

## Training data

`claimlens.synthetic` generates cases from 19 procedures, 40 hospitals in three city tiers, three product types and three bill layouts. Labels are Bernoulli draws from rule outcomes plus soft latent factors (price inflation, duplicates, unbundling, hospital propensity, concealed history) plus noise. Because the generator wrote the labels, the **ceiling** AUC (using the true generating probability) is about 0.88; the model cannot honestly beat that, and in this setting reaching it just means it recovered the simulator.

## Results (synthetic)

Release-gate run on the held-out test split (`make model`):

| Check | Result | Threshold |
|---|---|---|
| ROC AUC | 0.846 | ≥ 0.75 |
| Brier score | 0.147 | ≤ 0.20 |
| Calibration error (ECE) | 0.035 | ≤ 0.06 |
| Gain over rules-only baseline | +0.024 AUC | ≥ +0.02 |
| Subgroup AUC (product × 3, city tier × 3) | 0.818 – 0.870 | ≥ 0.68 and within 0.08 of overall |

Fresh-seed evaluation on 600 new synthetic cases (`make eval`, see `docs/EVAL_REPORT_SAMPLE.md`): model AUC 0.854 vs 0.821 for rules alone; ECE 0.056 vs 0.198; precision in the top 20% 0.81 vs 0.78. The small margin over the rules baseline is expected because the simulator derives most of its signal from the same rules.

The gate blocks promotion if any check fails, and the CI `model-gate` job runs it on every change.

## Limitations

- **Synthetic labels.** The real query/reduction process depends on insurer practice, TPA behaviour, regional and temporal drift, and reviewer inconsistency, none of which are modelled.
- **Parity checks are coarse.** Subgroups are product and city tier only. They do not cover age, gender, language, disability, income or any protected characteristic, and the synthetic data does not contain those. A real deployment needs a proper fairness review with real data before the model influences anyone's queue position.
- **Feedback loops.** If reviewers trust the score and read low-risk claims less carefully, labels collected later will be biased by the score itself. Track reviewer overrides and sample low-risk claims for audit.
- **Price book.** The reference prices are synthetic. Real use needs a price book from your own paid-claims history.
- **Extraction dependence.** Features inherit extraction errors. Extraction confidence is a feature, but the rule-based parser scores near 100% only because it shares vocabulary with the generator. Real scans go through OCR and an LLM extractor that has not been evaluated here.
- **Explanations are about the model, not causes.** "Hospital history raises the estimated chance" describes a statistical association, not a claim about the hospital's conduct.

## Monitoring and retraining (when real data exists)

Log score, band and reviewer outcome for every decision. Track calibration and AUC by month and by subgroup; alert on drift in input features and on rising reviewer overrides. Retrain on reviewed outcomes only, re-run the gate, and keep the previous bundle for rollback (`models/risk/CURRENT` points at the promoted version; bundles are immutable and hash-verified).

## Versioning

Bundle id `risk-<model-file-hash>-<training-data-id>` is stored in every `RiskScore.model_version` and every audit event, so any decision can be traced to the exact model that was shown.
