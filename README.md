# CrossFit Judge — Test Release (v2.3)

**English first · فارسی در ادامه (scroll down for Persian)**

---

## 1. What this is — and what it is *not*

CrossFit Judge is an **AI assistant for human judges** of online CrossFit competitions. An athlete uploads a workout video plus a few details (division, claimed reps/time). The system counts reps, decides *rep / no-rep* against the movement standards, explains every no-rep **in Persian**, reconciles the result with the athlete's claim, and produces an annotated review video and a one-page overview.

> ### ⚠️ TEST / EVALUATION RELEASE
> This build is an **experimental test version**. Its purpose is to **evaluate and improve the system together with Wodx** — it is **not** a production judge and its output must **never be the final ruling**.
>
> * It is **calibrated for one workout only**: *Thruster & Bar-Facing Burpee ladder, 18-15-12-9-6-3 (126 reps), 10-minute cap, For Time.*
> * Thresholds are **initial values**. They were verified on synthetic athletes and a synthetic video pipeline; **they still have to be tuned on real Wodx videos** (this is exactly what this test phase is for).
> * The system is deliberately **lenient** (`JUDGE_EASE=0.5`, ≈50 % more forgiving than the rulebook) and **never silently drops an ambiguous rep** — borderline reps are counted *and* flagged for a human judge.
> * Please send us the cases where the system disagrees with your judges (video time-stamp + what the correct call was). Those cases drive the next calibration round.

### How a run works
1. Upload (up to **500 MB** and **15 minutes**; MP4/MOV/WebM, ≥ 480p) with division and the athlete's claim (reps, or finish time / "time cap").
2. The workout clock starts at the **first frame of the video** and stops at the **last rep (#126) or at 10:00**, whichever comes first.
3. The engine follows a fixed **1…126 counter** (18 thrusters → 18 burpees → 15 → 15 → 12 → 12 → 9 → 9 → 6 → 6 → 3 → 3). At every slot it knows which movement to expect and only judges *that* movement.
4. Result: valid reps, no-reps with Persian reasons, a confidence per rep, claim-vs-detected check, a review queue for the judge, and the annotated video.

### Known limits of this release
* Calibrated for this one WOD; other movements/WODs need their own calibration.
* Best camera angle: **side or 45°** (some rules cannot be evaluated from straight-on).
* "Facing the bar vs. parallel" is not automatic yet. Confidence percentages are heuristic (not statistically calibrated yet).
* Pose extraction on **real** athlete videos is the main thing being evaluated in this phase.

---

## 2. Deploy with Docker (recommended)

### Requirements
* A Linux server (x86-64) with **Docker Engine ≥ 24** and the **Compose plugin** (`docker compose version`).
* **≥ 2 vCPU, 4 GB RAM** (4 vCPU / 8 GB recommended), **≥ 20 GB free disk**. *Indicative:* a 60-second 720p clip was analysed in ~30 s on 1 vCPU, so a full 10-minute run takes roughly **5 minutes per job per core**.
* Outbound internet **during the build** (Docker Hub, PyPI, npm) — or use the offline route below.

### Steps
```bash
unzip CrossFit-Judge-*.zip && cd CrossFit-Judge-*
cp .env.example .env
nano .env                      # set ACCESS_PASSWORD (and ACCESS_USER); adjust the rest if needed
docker compose up -d --build   # first build: several minutes
docker compose ps              # both services should become "healthy"
```
Open `http://<server-ip>:8080` (change with `WEB_PORT`). Quick checks:
```bash
curl http://localhost:8080/healthz                 # web  -> {"ok":true,...}
curl -u USER:PASS http://localhost:8080/api/judge/health   # engine -> "deps_ok":true,"ffmpeg_ok":true
```

### No internet on the server / different CPU architecture
Build on your own computer, ship the images:
```bash
./deploy/export-images.sh                          # builds linux/amd64 images -> crossfit-judge-images.tar.gz
scp crossfit-judge-images.tar.gz CrossFit-Judge-*.zip user@server:~
# on the server:
docker load < crossfit-judge-images.tar.gz
unzip CrossFit-Judge-*.zip && cd CrossFit-Judge-* && cp .env.example .env && nano .env
docker compose up -d --no-build
```

### HTTPS (optional)
Point a DNS name at the server, then in `.env` set `DOMAIN=judge.example.com` and `WEB_BIND=127.0.0.1`:
```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```
(Ports 80/443 must be open; Let's Encrypt certificates are automatic.) If the client already has a reverse proxy (nginx/Traefik), proxy to `web:3000`, allow request bodies ≥ 600 MB, and disable response buffering.

### Configuration (`.env`)
| Variable | Default | Meaning |
|---|---|---|
| `WEB_PORT` / `WEB_BIND` | `8080` / `0.0.0.0` | Published port / bind address |
| `ACCESS_USER` / `ACCESS_PASSWORD` | – | HTTP Basic auth for the whole site (leave empty to disable) |
| `JUDGE_WORKERS` | `1` | Parallel analyses (≈1 core + 1–2 GB RAM each) |
| `JUDGE_EASE` | `0.5` | Leniency: `0` = strict rulebook … `1` = very lenient |
| `JUDGE_RETENTION_DAYS` | `30` | Auto-delete videos/results older than N days (`0` = never) |
| `JUDGE_MAX_UPLOAD_BYTES` | `524288000` | Upload limit (500 MB) |
| `JUDGE_USE_BEEP` | `0` | `0` = clock starts at the first frame (Wodx protocol) |
| `JUDGE_ANNOTATE` | `1` | Render the annotated review video |

### Operations
```bash
docker compose logs -f             # live logs (both services)
docker compose restart             # restart
git pull / unzip a new version, then:  docker compose up -d --build     # update (data is kept)
docker compose down                # stop (data is kept)   |   docker compose down -v   # stop AND delete all data
# backup (uploads + results DB):
docker run --rm -v crossfit-judge_judge_state:/s -v "$PWD":/b alpine tar czf /b/judge-state.tgz -C /s .
```
Data lives in the Docker volume `judge_state`. The engine port (8001) is **not** exposed to the host. Uploaded videos are personal data — set `JUDGE_RETENTION_DAYS` according to the client's policy.

### Troubleshooting
| Symptom | Cause / fix |
|---|---|
| "Analysis engine is starting up" | The engine needs ~20–60 s after start; the UI retries automatically. |
| "ffprobe/ffmpeg is not installed" | Only in non-Docker runs: install ffmpeg (`brew install ffmpeg` / `apt install ffmpeg`). |
| Upload rejected: size / duration / resolution | Limits: 500 MB, 15 min, ≥ 480p. |
| 413 / upload stalls behind a proxy | Raise the proxy body limit (≥ 600 MB) and disable buffering. |
| Build fails to download packages | Use the offline route (`deploy/export-images.sh`). |
| Disk filling up | Lower `JUDGE_RETENTION_DAYS`; check `docker system df`. |

---

## 3. Local development (without Docker)
```bash
brew install ffmpeg            # or: sudo apt install -y ffmpeg libgl1 libegl1 fonts-dejavu-core
cd mini-services/crossfit-judge && python3 -m venv venv && . venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests -q      # engine tests
cd ../.. && bun install && bun run dev     # or: npm install && npm run dev  → http://localhost:3000
```
In dev the web app starts the Python engine itself. Set `JUDGE_ENGINE_URL` to use an engine running elsewhere.

### Repository layout
```
src/                      Next.js UI + /api/judge proxy (bilingual EN/FA)
mini-services/crossfit-judge/   Python engine (FastAPI, MediaPipe, ffmpeg)
  core/ movements/ judging/     counter, movement state machines, scoring
  data/                          WOD definition, divisions, pose model
Dockerfile, docker-compose*.yml  deployment
docs/CHANGES_v2.1_FA.md          change log (Persian)
```

---
---

# داور هوشمند کراس‌فیت — نسخه آزمایشی (v2.3)

## ۱. این سیستم چیست و چه چیزی **نیست**

داور هوشمند کراس‌فیت یک **دستیار هوش مصنوعی برای داوران انسانی** مسابقات آنلاین کراس‌فیت است. ورزشکار ویدیوی تمرین را به‌همراه چند اطلاعات (رده، تعداد رپ یا زمان ادعایی) آپلود می‌کند. سیستم رپ‌ها را می‌شمارد، طبق استانداردهای حرکت **رپ / نو-رپ** را تعیین می‌کند، دلیل هر نو-رپ را **به فارسی** می‌نویسد، نتیجه را با ادعای ورزشکار مقایسه می‌کند و یک ویدیوی بازبینی نشانه‌گذاری‌شده و یک اورویو می‌دهد.

> ### ⚠️ نسخه تستی / آزمایشی
> این نسخه یک **نسخه‌ی آزمایشی** است و هدفش **ارزیابی و بهبود سیستم همراه با وادکس** است؛ **داور نهایی نیست** و خروجی‌اش هرگز نباید حکم نهایی تلقی شود.
>
> * فقط برای **یک واد** کالیبره شده است: **نردبان تراستر و باربل‌فیسینگ برپی، ۱۸-۱۵-۱۲-۹-۶-۳ (۱۲۶ تکرار)، تایم‌کپ ۱۰ دقیقه، For Time.**
> * آستانه‌ها **مقدار اولیه** هستند؛ روی ورزشکار و ویدیوی شبیه‌سازی‌شده راستی‌آزمایی شده‌اند و **هنوز باید با ویدیوهای واقعی وادکس تنظیم شوند** — همین هدف این مرحله‌ی تست است.
> * سیستم عمداً **منعطف** است (`JUDGE_EASE=0.5`، حدود ۵۰٪ آسان‌تر از آیین‌نامه) و **هیچ رپ مبهمی را بی‌صدا حذف نمی‌کند**؛ رپ‌های مرزی شمرده می‌شوند و برای داور علامت می‌خورند.
> * لطفاً مواردی که نتیجه‌ی سیستم با نظر داوران شما فرق دارد را برایمان بفرستید (زمان در ویدیو + تصمیم درست). همین موارد دور بعدی کالیبراسیون را می‌سازند.

### روند کار
۱. آپلود (حداکثر **۵۰۰ مگابایت** و **۱۵ دقیقه**؛ MP4/MOV/WebM، حداقل ۴۸۰p) همراه با رده و ادعای ورزشکار (تعداد رپ، یا زمان پایان / «تایم‌کپ»).
۲. ساعت واد از **فریم اول ویدیو** شروع می‌شود و با **آخرین رپ (۱۲۶ام) یا ۱۰:۰۰** (هرکدام زودتر) متوقف می‌شود.
۳. موتور طبق یک **شمارنده‌ی ثابت ۱ تا ۱۲۶** پیش می‌رود (۱۸ تراستر ← ۱۸ برپی ← ۱۵ ← ۱۵ ← ۱۲ ← ۱۲ ← ۹ ← ۹ ← ۶ ← ۶ ← ۳ ← ۳). در هر اسلات می‌داند چه حرکتی باید ببیند و فقط همان را داوری می‌کند.
۴. خروجی: رپ‌های معتبر، نو-رپ‌ها با دلیل فارسی، درصد اطمینان هر رپ، تطبیق ادعا با شمارش سیستم، صف بازبینی برای داور و ویدیوی نشانه‌گذاری‌شده.

### محدودیت‌های شناخته‌شده‌ی این نسخه
* فقط برای همین یک واد کالیبره شده؛ حرکات/وادهای دیگر کالیبراسیون جداگانه می‌خواهند.
* بهترین زاویه‌ی دوربین: **پهلو یا ۴۵ درجه** (بعضی قوانین از روبرو قابل ارزیابی نیستند).
* قانون «روبروی هالتر بودن (نه موازی)» هنوز خودکار نیست؛ درصدهای اطمینان ابتکاری‌اند و هنوز آماری کالیبره نشده‌اند.
* استخراج اسکلت روی **ویدیوی واقعی** ورزشکاران، مهم‌ترین چیزی است که در این مرحله ارزیابی می‌شود.

---

## ۲. استقرار با Docker (پیشنهادی)

### پیش‌نیازها
* سرور لینوکس (x86-64) با **Docker Engine ≥ 24** و پلاگین **Compose** (`docker compose version`).
* **حداقل ۲ هسته CPU و ۴ گیگ RAM** (پیشنهاد: ۴ هسته / ۸ گیگ) و **حداقل ۲۰ گیگ فضای خالی**. *تقریبی:* یک کلیپ ۶۰ ثانیه‌ای ۷۲۰p روی ۱ هسته حدود ۳۰ ثانیه طول کشید؛ پس یک اجرای کامل ۱۰ دقیقه‌ای حدود **۵ دقیقه به‌ازای هر هسته** است.
* اینترنت **هنگام build** (Docker Hub، PyPI، npm) — یا از روش آفلاین پایین استفاده کنید.

### مراحل
```bash
unzip CrossFit-Judge-*.zip && cd CrossFit-Judge-*
cp .env.example .env
nano .env                      # ACCESS_PASSWORD (و ACCESS_USER) را تنظیم کنید
docker compose up -d --build   # بار اول چند دقیقه طول می‌کشد
docker compose ps              # هر دو سرویس باید healthy شوند
```
آدرس: `http://<آی‌پی-سرور>:8080` (با `WEB_PORT` قابل تغییر). بررسی سریع:
```bash
curl http://localhost:8080/healthz
curl -u USER:PASS http://localhost:8080/api/judge/health     # باید deps_ok و ffmpeg_ok برابر true باشد
```

### سرور بدون اینترنت / معماری متفاوت
روی کامپیوتر خودتان build کنید و ایمیج‌ها را منتقل کنید:
```bash
./deploy/export-images.sh                          # ایمیج linux/amd64 → crossfit-judge-images.tar.gz
scp crossfit-judge-images.tar.gz CrossFit-Judge-*.zip user@server:~
# روی سرور:
docker load < crossfit-judge-images.tar.gz
unzip CrossFit-Judge-*.zip && cd CrossFit-Judge-* && cp .env.example .env && nano .env
docker compose up -d --no-build
```

### HTTPS (اختیاری)
یک نام دامنه را به سرور وصل کنید و در `.env` مقدار `DOMAIN=judge.example.com` و `WEB_BIND=127.0.0.1` را بگذارید:
```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```
(پورت‌های ۸۰ و ۴۴۳ باید باز باشند؛ گواهی Let's Encrypt خودکار است.) اگر کارفرما از قبل reverse proxy دارد (nginx/Traefik)، به `web:3000` پروکسی کنید، حجم بدنه‌ی درخواست را ≥ ۶۰۰ مگابایت بگذارید و buffering پاسخ را خاموش کنید.

### تنظیمات (`.env`)
| متغیر | پیش‌فرض | معنی |
|---|---|---|
| `WEB_PORT` / `WEB_BIND` | `8080` / `0.0.0.0` | پورت منتشرشده / آدرس bind |
| `ACCESS_USER` / `ACCESS_PASSWORD` | – | رمز Basic روی کل سایت (خالی = غیرفعال) |
| `JUDGE_WORKERS` | `1` | تعداد آنالیز هم‌زمان (هرکدام ≈ ۱ هسته + ۱ تا ۲ گیگ RAM) |
| `JUDGE_EASE` | `0.5` | میزان انعطاف: `0` = آیین‌نامه‌ی سخت … `1` = خیلی منعطف |
| `JUDGE_RETENTION_DAYS` | `30` | حذف خودکار ویدیو/نتیجه‌ی قدیمی‌تر از N روز (`0` = هرگز) |
| `JUDGE_MAX_UPLOAD_BYTES` | `524288000` | سقف حجم آپلود (۵۰۰ مگابایت) |
| `JUDGE_USE_BEEP` | `0` | `0` = ساعت از فریم اول ویدیو شروع می‌شود (پروتکل وادکس) |
| `JUDGE_ANNOTATE` | `1` | ساخت ویدیوی بازبینی نشانه‌گذاری‌شده |

### نگهداری
```bash
docker compose logs -f             # لاگ زنده
docker compose restart             # راه‌اندازی مجدد
# به‌روزرسانی: نسخه‌ی جدید را باز کنید و:  docker compose up -d --build   (داده‌ها می‌مانند)
docker compose down                # توقف (داده‌ها می‌مانند)   |   docker compose down -v   # توقف و حذف کل داده‌ها
# پشتیبان‌گیری (ویدیوها + دیتابیس نتایج):
docker run --rm -v crossfit-judge_judge_state:/s -v "$PWD":/b alpine tar czf /b/judge-state.tgz -C /s .
```
داده‌ها در volume با نام `judge_state` هستند. پورت موتور (۸۰۰۱) به بیرون **باز نمی‌شود**. ویدیوهای آپلودشده داده‌ی شخصی‌اند؛ `JUDGE_RETENTION_DAYS` را طبق سیاست کارفرما تنظیم کنید.

### عیب‌یابی
| نشانه | علت / راه‌حل |
|---|---|
| «Analysis engine is starting up» | موتور بعد از شروع ۲۰ تا ۶۰ ثانیه آماده‌سازی می‌خواهد؛ رابط خودکار دوباره تلاش می‌کند. |
| «ffprobe/ffmpeg is not installed» | فقط در اجرای بدون Docker: ffmpeg نصب کنید (`brew install ffmpeg` / `apt install ffmpeg`). |
| آپلود رد شد: حجم / مدت / رزولوشن | محدودیت‌ها: ۵۰۰ مگابایت، ۱۵ دقیقه، حداقل ۴۸۰p. |
| خطای 413 یا گیرکردن آپلود پشت پروکسی | سقف بدنه‌ی پروکسی را ≥ ۶۰۰ مگابایت کنید و buffering را خاموش کنید. |
| build نمی‌تواند بسته دانلود کند | از روش آفلاین (`deploy/export-images.sh`) استفاده کنید. |
| پرشدن دیسک | `JUDGE_RETENTION_DAYS` را کمتر کنید؛ `docker system df` را ببینید. |

---

## ۳. توسعه‌ی محلی (بدون Docker)
```bash
brew install ffmpeg            # یا: sudo apt install -y ffmpeg libgl1 libegl1 fonts-dejavu-core
cd mini-services/crossfit-judge && python3 -m venv venv && . venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests -q      # تست‌های موتور
cd ../.. && bun install && bun run dev     # یا: npm install && npm run dev  ← http://localhost:3000
```
در حالت توسعه، برنامه‌ی وب خودش موتور پایتون را اجرا می‌کند. برای استفاده از موتوری که جای دیگری اجرا می‌شود `JUDGE_ENGINE_URL` را تنظیم کنید.

### ساختار پروژه
```
src/                      رابط Next.js + پروکسی /api/judge (دوزبانه EN/FA)
mini-services/crossfit-judge/   موتور پایتون (FastAPI، MediaPipe، ffmpeg)
  core/ movements/ judging/     شمارنده، ماشین‌حالت حرکات، امتیازدهی
  data/                          تعریف واد، رده‌ها، مدل پوز
Dockerfile, docker-compose*.yml  استقرار
docs/CHANGES_v2.1_FA.md          تاریخچه‌ی تغییرات
```
