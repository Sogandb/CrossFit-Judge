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

---
Task ID: 4
Agent: main (Super Z)
Task: How to handle movement transitions during WODs (transition risk matrix) + how to handle technique variants (kipping/butterfly/mixed pull-ups) in judging

Work Log:
- Ran 5 web searches: CrossFit pull-up standards, kipping vs butterfly biomechanics, temporal action boundary detection, HMM sequential activity, fine-grained action recognition
- Key finds: official CrossFit PDF (18.5) "Dead hang, kipping or butterfly pull-ups are allowed as long as all the requirements are met" = standards are OUTCOME-based not technique-based; BoxRox 22.3 "any style permitted"; JSES study (strict/kipping/butterfly differ in muscle activation but same outcome checkpoints); TAD boundary detection (Boundary-Recovering Network arXiv 2408.09354); adaptive HMM activity transitions (PMC5729042); BMVC 2025 fine-grained action recognition (intra-class variation)
- Composed: (1) transition solution = explicit TRANSITION state + guard/confirmation window + expected-sequence constraint + rep-completion gate + task-level hysteresis + spatial anchors + pair-specific fatigue-inclusive test matrix; (2) variant solution = separate validity layer (outcome-based, technique-agnostic) from technique layer (analytics only), mixed-variant sets become non-problem by construction, technique_freedom flag per movement for technique-mandated standards (HSPU strict vs kipping per division)

Stage Summary:
- Transition engineering: orchestrator FSM with TRANSITION states, boundary detection with confirmation windows, premature-transition detection
- Variant engineering: outcome-based predicates (start: arms extended; credit: chin breaks bar plane) are variant-invariant; mixed technique mid-set requires no special handling; only encode technique constraints where the RULEBOOK mandates them (flag technique_freedom per movement)
- New metrics: boundary F1 (±0.5s), task attribution accuracy, variant-invariance delta

---
Task ID: 5
Agent: main (Super Z)
Task: Camera angle strategy (sagittal vs frontal per movement, fixed vs changing mid-WOD) + handling hijab-wearing athletes (occluded landmarks) in pose estimation judging

Work Log:
- Ran 5 web searches: CrossFit camera angle rules, hijab/loose clothing pose estimation, multi-view fusion, occlusion benchmarks (OCHuman), pose fairness across demographics
- Key finds: official CrossFit guidance = fixed 3/4 view whole video, camera >=90cm height, no cuts (Games best practices + Quarterfinals FAQ + L4 course 45deg); multi-view fusion without prior calibration (PMC11644880 stereo MediaPipe); loose-clothing pose estimation (arXiv 2212.04820); occlusion-robust HPE via occlusion augmentation (arXiv 2304.12069); OCHuman benchmark + occlusion measurement for reliable HPE (ACM); Sony AI + AAAI-23 fairness evaluations of HPE across demographic groups (performance discrepancies for ALL models)
- Composed: (1) camera strategy = fixed 3/4 diagonal as default rule + optional dual fixed cameras (view arbitration/fusion per task) + per-movement preferred_view metadata in DSL + Day-0 camera plan generation; NO dynamic angle changes mid-WOD; (2) hijab strategy = landmark-availability contract per movement, standards re-expression with silhouette/geometric proxies (jaw profile from side view, arm-vertical alignment instead of ears), segmentation-based fallback, occlusion augmentation training, hijabi athletes in golden dataset from day 1 + accuracy parity metric, rules adjustments (form-fitting sports hijab, face profile visible), privacy as trust feature (on-device processing, face blur in review clips)

Stage Summary:
- Camera: fixed 3/4 view is the official+engineering compromise; dual-camera optional upgrade; per-task view metadata + escalation when required view unavailable
- Hijab: measure differently, not judge differently — same outcome standards, alternative landmark geometry; parity metric mandatory; privacy = marketing advantage in target market
