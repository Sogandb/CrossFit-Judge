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

---
Task ID: 6
Agent: main (Super Z)
Task: Meta-question — what critical questions has the user NOT asked yet; golden insights affecting system accuracy and efficiency

Work Log:
- Ran 4 grounding searches: clock-visible-in-frame requirement (CONFIRMED official: "A clock must be visible throughout the workout"), CrossFit score appeals process (83 adjustments in 2022, 130+ adjustments/10 appeals in one 2025 review), video tamper forensics, HITL review tooling
- Synthesized 10 unasked-question golden list in 3 categories: accuracy (clock/time anchoring via OCR + duration cross-check, pre-workout setup verification phase, audio as cross-check signal via ASR on judge count calls, asymmetric error policy = auto-validate only), efficiency (review console IS the product, two-tier cheap-skim + deep-pass processing, declared-score reconciliation routing), operations (formal appeals workflow, business continuity/degraded mode, go/no-go pilot criteria)

Stage Summary:
- 10 golden unasked topics delivered with official source grounding
- Top 3 most critical: (1) clock anchoring & time verification, (2) review console UX = real throughput bottleneck, (3) declared-score reconciliation = actual product workflow (verification, not discovery)
- All prior research JSONs retained in /home/z/my-project/research/ (30+ files, ~60 searches total across 6 task IDs)

---
Task ID: 7
Agent: main (Super Z)
Task: Review user's initial CrossFit-Judge v1 implementation (github.com/Sogandb/CrossFit-Judge) against the 6-session agreed architecture + fresh research; deliverables = review-only report (NO code changes), per user instruction

Work Log:
- Cloned repo to /home/z/my-project/repo-review; read 100% of Python service (24 files: main, worker, config, core, 7 movements, scorer, reporting, utils, tests) + key frontend files (page.tsx, 9 crossfit components, api client, python-server, proxy route)
- Set up runtime: installed mediapipe/opencv/fastapi/etc in venv, downloaded pose_landmarker_full model
- Ran project self-test (all 3 critical tests PASS); wrote /home/z/my-project/scripts/verify_bugs.py to test 4 suspected findings — ALL CONFIRMED: (1) KettlebellSwing FSM dead (4.0-degree hysteresis applied to 0-1 ratio signal -> stuck in IDLE forever, 0 reps from 6 full swings; Burpee overrides classifier, KB does not), (2) For Time score = full video duration (114s work in 600s video -> 10:00), (3) Tabata counts rest-window reps (20 reps counted), (4) no_rep_reason_fa/en fields semantically swapped (English text in fa field, snake_case key in en field; frontend prefers en -> raw key shown)
- Ran 13 fresh web searches saved to research/r7_*.json (~80 results): PubMed (2D frontal-plane knee angle validity r~0.20), Frontiers (squat projection bias), official CrossFit Games (2026 rulebook clock-visible rule, video review best practices, real 25.1 = lateral burpees over DB), AMRAP score = rounds+reps convention, Tabata 20/10 protocol, EMOM semantics, MediaPipe num_poses multi-person limits, PyAV VFR timestamp issue, FastAPI CPU-bound queue best practices, BlazePose vs RTMPose/RTMW benchmarks, FSM+hysteresis rep counting standard
- Built compliance matrix of 29 agreed components across 3 layers: 7 present / 3 partial / 19 absent (Layer1 ~56%, Layer2 ~18%, Layer3 ~22%)
- Additional findings: sequencer fragility (no TRANSITION/guard/recovery; one missed rep desyncs everything, no flag), timer anchored to video frame 0 (setup time eats time cap; no clock OCR), EMOM/Tabata formats label-only, DSL lacks rounds/ladders(21-15-9)/blocks/tiebreak/versioning, squat uses knee-angle proxy instead of hip-below-knee standard, pull-up chin via nose proxy (stricter than official) + global-min bar line estimation, burpee thresholds lenient (0.35 descent, 0.02 jump, -0.03 overhead) and standards vary per WOD, pushup/KB thresholds frame-dependent (not scale-invariant), visibility gate 0.15 too low, num_poses=1 no person-consistency, OpenCV VFR drift, 15fps marginal for fast movements, 300s subprocess timeout + unlimited concurrency vs 5-20min video goal, audio stripped (-an) from review video, English-only UI for Iranian market, repo hygiene (custom.db, zips, unused deps, dead settings), synthetic-only testing
- Generated full Persian RTL docx report: /home/z/my-project/download/CrossFit-Judge-v1-Code-Review-Report-FA.docx (23 pages, cover R1-RTL + TOC + 7 tables + 12 sections; built via scripts/report_gen/{content1,content2,generate}.js + postprocess.py per docx skill rules; postcheck 0 errors; VLM visual verification of cover + body pages passed)

Stage Summary:
- Verdict: solid v1 engineering core (FSM+hysteresis+debounce, data-driven standards, expected-sequence constraint in simplest form, per-rep evidence log, robust infra) but NOT competition-ready: 1 of 6 movements fully broken, 2 scoring formats wrong, sequencer has no recovery, no time anchor/audio/anti-fraud
- Prioritized action plan: P0 = 6 quick fixes (KB hysteresis, For Time finish time, Tabata windows, fa/en swap, calibration on first-detected frame, keep audio); P1 = sequencer resilience + full WOD DSL + time anchor + geometric standards + processing queue + visibility gating; P2 = review console, Persian RTL, golden dataset + metrics, hijab package, score reconciliation
- No code changes made (user rule); all findings reproducible via scripts/verify_bugs.py

---
Task ID: 8
Agent: main (Super Z)
Task: Consultation (no code changes): compare (A) direct video upload to system vs (B) YouTube upload + link extraction, for ~2000 athletes; cheapest optimal extraction method; whether/how to skip the athlete intro/profiling segment without hurting evaluation

Work Log:
- Ran 11 fresh web searches saved to research/r8_*.json (~80 results): yt-dlp PO-token/bot-detection issues (GitHub #17368 #13067 #7716, renderio, reddit), YouTube ToS on third-party downloads + 2026 US DMCA ruling (medianama), S3 presigned multipart best practices (AWS official), storage pricing 2025 (B2 $0.006/GB, R2 $0.015/GB zero-egress, Wasabi $0.0049/GB, S3 $0.023/GB + egress), official CrossFit video submission rules ("YouTube is the ONLY accepted video submission platform", publicly viewable, uncut), video-compression impact on pose estimation (biorxiv: train on compressed to close gap; MDPI compressed-sensing study), YAMNet audio event classifier (Google, 521 AudioSet classes) + AWS Rekognition sports whistle detection, exercise temporal segmentation (arXiv 2507.12245, 2004.10026), yt-dlp mass-download IP blacklisting (PeerTube #5688, datacenter IPs flagged), tus resumable upload protocol (IETF, Cloudflare Stream recommends for unreliable connections), specialized workout-video platforms (WODProof, StreamFit, WeTime)
- Composed full Persian consultation answer in chat: comparison table A vs B; scale math (2000 videos ≈ 2.4 TB/event; $12-40/mo on B2/Wasabi/R2 vs S3 ~$120/mo with egress; GPU inference $50-200/event); yt-dlp practical extraction recipe + operational/legal risks; recommendation = hybrid (direct upload primary via presigned multipart/tus + optional YouTube link as public evidence/offsite backup)
- Intro-skip design: never physically cut; store t_start/t_end/preroll metadata; analysis window = [t_start - preroll(5-10s), t_end]; 4 reasons intro must leave the ANALYSIS window (false reps from demo/warm-up, time-anchor corruption - ties to v1 audit bug #2, calibration pollution - v1 calibrates on first frame, ~10-15% wasted inference); T_start multi-signal detector (YAMNet audio beep/countdown + OCR clock reset + motion energy + optional declared timestamp) with confidence fusion and human-in-the-loop fallback in review console; preroll doubles as clean calibration frame source; rulebook lever (require visible timer + clear start signal) to make detection reliable; ties to audit finding that v1 strips audio (-an) which must be reverted

Stage Summary:
- Verdict: both routes viable; direct upload is ToS-safe, quality-pure, deadline-robust and cheap at scale (~$50-250 total per event all-in); YouTube-only is domain-conventional (official CrossFit standard) and zero-storage-cost but the automated-download step for analysis violates YouTube ToS and is operationally fragile at 2000-video scale (PO tokens, IP bans) - mitigate with rolling ingest, residential egress, canary tests, evidence snapshots, fallback direct upload for failures/appeals
- Intro: keep in file (zero negative impact + future value for deferred equipment-profiling phase + evidence integrity), exclude from analysis window via offset metadata (staying inside analysis = direct score corruption)
- No deliverable files this task (chat consultation only); all sources retained in research/r8_*.json
