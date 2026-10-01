# Worklog

---
Task ID: 1
Agent: main (Super Z)
Task: Research feasibility of AI pose-estimation judge assistant for online CrossFit competitions + list top 10 challenges (user questions 1 & 2, Persian)

Work Log:
- Ran 10 web searches via z-ai CLI, saved JSON results to /home/z/my-project/research/
- Topics: CrossFit Open judging/validation, pose estimation rep counting research, AI fitness apps, occlusion/angle/lighting challenges, CrossFit online cheating/fraud, exercise recognition reviews, AI judging in sports (Fujitsu/ISU), complex movement detection, domain gap generalization
- Compiled 15+ credible sources: PMC/NCBI peer-reviewed studies, IEEE, Springer, ResearchGate, arXiv, Reuters, Forbes, CACM, official CrossFit Games pages, commercial apps (REP AI, Sculptor, Skeletal PT)

Stage Summary:
- Q1 verdict: feasible as a human-in-the-loop judge ASSISTANT (rep counting + ROM checks for core movements are proven, 92-97% accuracies reported); full autonomous judging not yet feasible
- Q2: 10 challenges compiled (occlusion, camera angle, motion blur/frame rate, depth ambiguity, complex movements/lack of CrossFit datasets, domain gap, cheating/adversarial, equipment & load verification, scalability/cost, liability & community acceptance + privacy)
- Research data retained in /home/z/my-project/research/*.json for later phases of the project

---
Task ID: 2
Agent: main (Super Z)
Task: How to encode/define CrossFit WODs (movement transitions, combos, rep schemes, formats) for the judging system + how to improve per-workout evaluation accuracy

Work Log:
- Ran 10 more web searches: temporal action segmentation, RepNet, FSM exercise phase detection, action quality assessment surveys, FHIR physical-activity schema, multi-exercise LSTM classification, WOD format taxonomy, hierarchical action recognition, angle thresholds
- Key finds: MDPI "A Movement Description Language for Functional Training" (DSL for exercises, interpretable phase detection), SAGE FSM rehab segmentation paper, RepNet (Google/DeepMind), BiLSTM real-time exercise classification (arXiv 2411.11548), AQA surveys (arXiv 2412.11149, Springer), HL7 FHIR Physical Activity IG
- Composed 3-layer architecture answer: Movement Library (FSM) + WOD DSL (JSON) + Runtime Interpreter (hierarchical state machines with expected-sequence constraint) + accuracy improvement loop

Stage Summary:
- Core design: system = WOD interpreter (compiler analogy), not open-world action recognizer; workout definition constrains the search space
- Improvement loop: golden dataset from public Open videos, metrics (MAE/OBO, no-rep F1, score exact-match), threshold calibration with hysteresis, ensembles, temporal plausibility priors, human-in-the-loop flywheel

---
Task ID: 3
Agent: main (Super Z)
Task: Strategy for preparing judge-assistant system for next competition round when WOD is unknown until close to event but movement pool is known; broad-coverage vs focused-depth question

Work Log:
- Ran 7 web searches: Open announcement timeline, historical movement frequency stats, few-shot action recognition, long-tail learning, 2024/2025 Open workouts, MLOps deploy practices, sports screening
- Key finds: official Open timeline (Thu 12pm PT release, Mon 5pm PT deadline, Wed validation); movement frequency data (thrusters 12-13x, burpees 10x, DU/T2B/CTB most common); movement pairing stats (Zoar); few-shot AR review (arXiv 2407.14744); long-tail systematic review (arXiv 2408.00483); MLOps freeze/rollout practices
- Composed hybrid strategy: full movement LIBRARY (data layer, cheap) + tiered deep validation (Tier 1 announced pool / Tier 2 historical / Tier 3 rare+fallback), 4-day post-announcement runbook, shadow-run rehearsal on public 2024/2025 Open videos, camera rule control as accuracy lever

Stage Summary:
- Answer: "Library broad, Perception deep" — define all movements now (cheap data), concentrate golden-dataset + calibration effort on known pool weighted by historical frequency
- 4-day instantiation runbook (Day 0 parse WOD->DSL, Day 1 dress rehearsal, Day 2-3 shadow run, Day 4 production)
- Extra levers: control video submission rules to constrain input distribution; freeze model changes before event; auto-escalation fallback for uncovered movements
