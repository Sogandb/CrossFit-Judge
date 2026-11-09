# راهنمای استقرار روی سرور کارفرما (Ubuntu + Docker)

مشخصات اعلام‌شده: ۴ تا ۶ هسته CPU، ۸ تا ۱۰ گیگ RAM، SSD ۱۰۰ گیگ، سرور خام، دسترسی SSH/RDP، دامنه/ساب‌دامین ممکن، پورت‌ها قابل‌باز.
این مشخصات برای نسخه‌ی تستی **کافی و مناسب** است. با `JUDGE_WORKERS=2` دو آنالیز هم‌زمان اجرا می‌شود؛ هر آنالیز ویدیوی ۱۰ دقیقه‌ای در حدود چند دقیقه تمام می‌شود (روی ۱ هسته، تقریباً ۵ دقیقه به‌ازای هر ویدیوی ۱۰ دقیقه‌ای؛ اندازه‌گیری تقریبی).

---
## الف) قبل از اینکه سرور را بدهند (همین حالا آماده کن)

### ۱) از کارفرما این چیزها را بپرس (یک پیام)
۱. سیستم‌عامل **Ubuntu 22.04 یا 24.04 (x86-64)** باشد، نه ویندوز. (RDP روی لینوکس فقط برای دسترسی گرافیکی است؛ ما با SSH کار می‌کنیم.)
۲. نوع مجازی‌سازی **KVM/VMware** باشد (نه OpenVZ/LXC که Docker روی آن‌ها معمولاً کار نمی‌کند).
۳. سرور به **اینترنت خروجی** دسترسی دارد؟ مخصوصاً به `download.docker.com`، `registry-1.docker.io` و `github.com`؟ (اگر نه، مسیر «آفلاین» پایین را برویم.)
۴. کاربر با دسترسی **sudo** و **SSH** (ترجیحاً با کلید). آی‌پی سرور.
۵. **ساب‌دامین** (مثلاً `judge.company.ir`) را به آی‌پی سرور وصل کنند (رکورد A) و پورت‌های **80 و 443** روی فایروال/پنل باز باشند. اگر دامنه ممکن نیست: فقط پورت **8080** (بدون HTTPS؛ حتماً رمز بگذار و ترجیحاً پشت VPN/فایروال).
۶. آیا سیاست خاصی برای نگهداری ویدیوها دارند؟ (پیش‌فرض: حذف خودکار بعد از ۳۰ روز.)

### ۲) روی گیت‌هاب
۱. کد را مثل قبل با تگ **v2.4** (برنچ `release/v2.4`) پوش کن.
۲. در GitHub → **Actions** → `build-images` → **Run workflow**. این کار ایمیج‌ها را برای `linux/amd64` می‌سازد، خودش **تست دودی واقعی** (آپلود ویدیو → آنالیز → ویدیوی بازبینی) روی آن‌ها می‌زند، و فایل `crossfit-judge-images.tar.gz` را به‌عنوان Artifact می‌دهد (۱۴ روز می‌ماند). این خودِ `docker build` را هم تست می‌کند، کاری که من روی سیستم خودم نتوانستم.
۳. Artifact را دانلود کن (برای مسیر آفلاین لازم می‌شود). **اگر Actions قرمز شد، پیش از سرور خطا را بفرست.**

### ۳) روی کامپیوتر خودت
- فایل `.env` را آماده کن (از `.env.example`): رمز قوی برای `ACCESS_PASSWORD`، و برای این سرور:
  ```
  WEB_PORT=8080          # (اگر دامنه نیست و فقط آی‌پی است، می‌توانی 80 بگذاری)
  JUDGE_WORKERS=2
  JUDGE_RETENTION_DAYS=30
  JUDGE_EASE=0.5
  ```
  (برای HTTPS با دامنه: `DOMAIN=judge.company.ir` و `WEB_BIND=127.0.0.1`.)
- زیپ پروژه + `.env` + (در صورت مسیر آفلاین) `crossfit-judge-images.tar.gz` را کنار هم نگه دار.

---
## ب) بعد از اینکه سرور را دادند (به ترتیب)

```bash
# ۱) ورود
ssh USER@SERVER_IP

# ۲) بررسی پیش‌نیازها (فایل deploy/server-preflight.sh را اول کپی کن: scp deploy/server-preflight.sh USER@SERVER_IP:~)
bash server-preflight.sh          # هر WARN/FAIL را برای من بفرست

# ۳) نصب Docker (با اینترنت). فایل deploy/install-docker-ubuntu.sh را هم کپی کن
sudo bash install-docker-ubuntu.sh --firewall
exit  # خروج و ورود دوباره (گروه docker)
ssh USER@SERVER_IP
docker run --rm hello-world

# ۴) انتقال پروژه (از کامپیوتر خودت)
scp CrossFit-Judge-v2.4-test.zip .env USER@SERVER_IP:~
# (مسیر آفلاین:  scp crossfit-judge-images.tar.gz USER@SERVER_IP:~ )

# ۵) روی سرور
sudo apt-get install -y unzip
unzip CrossFit-Judge-v2.4-test.zip && cd CrossFit-Judge-v2.4-test
mv ~/.env .env && chmod 600 .env

# ۶-الف) با اینترنت (build روی خود سرور؛ چند دقیقه)
docker compose up -d --build
# ۶-ب) آفلاین (ایمیج‌ها از Artifact)
docker load < ~/crossfit-judge-images.tar.gz
docker compose up -d --no-build

# ۷) صبر تا healthy
docker compose ps

# ۸) تست دودی واقعی
python3 deploy/smoke_test.py http://localhost:8080 wodx:YOUR_PASSWORD
```
باید `[smoke] PASS` ببینی. سپس از مرورگر `http://SERVER_IP:8080` را باز کن و با ویدیوی واقعی یک بار امتحان کن.

### HTTPS با ساب‌دامین (پیشنهادی برای تحویل به کارفرما)
در `.env`: `DOMAIN=judge.company.ir` و `WEB_BIND=127.0.0.1` ، سپس:
```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```
(پورت ۸۰/۴۴۳ باز و رکورد DNS درست باشد؛ گواهی خودکار صادر می‌شود.) بعد از آن، آدرس نهایی: `https://judge.company.ir`.

---
## پ) تحویل به کارفرما
۱. آدرس + نام کاربری/رمز را در یک کانال امن بده (نه ایمیل متنی ساده).
۲. این‌ها را کنارش بنویس: نسخه‌ی تستی است؛ فقط برای واد «تراستر و باربل‌فیسینگ برپی ۱۸-۱۵-۱۲-۹-۶-۳»؛ زاویه‌ی فیلم‌برداری **پهلو یا ۴۵ درجه، کل بدن، دوربین ثابت**؛ حداکثر ۵۰۰MB و ۱۵ دقیقه؛ خروجی «کمک به داور» است نه حکم نهایی.
۳) از آن‌ها بخواه برای هر ویدیو، نتیجه‌ی داور خودشان را (رپ/نورپ هر تکرار) در csv بدهند (`rep,verdict`)، تا با `tools/compare_human.py` دقیق مقایسه کنیم.

---
## ت) نگهداری
```bash
docker compose logs -f            # لاگ
docker compose ps                 # وضعیت
docker compose restart            # راه‌اندازی مجدد
df -h / ; docker system df        # فضای دیسک
docker compose up -d --build      # به‌روزرسانی بعد از جایگزینی فایل‌ها (داده‌ها می‌مانند)
```
بعد از ریبوت سرور، سرویس‌ها خودکار بالا می‌آیند (`restart: unless-stopped` + Docker فعال در systemd).
پشتیبان: دستور README (بخش Operations).

## ث) ریسک‌ها و راه‌حل
| ریسک | راه‌حل |
|---|---|
| سرور به Docker Hub/GitHub دسترسی ندارد | مسیر آفلاین (Artifact) + از IT یک mirror/پروکسی بخواه؛ نصب Docker آفلاین را در صورت نیاز جداگانه آماده می‌کنم |
| سرور ویندوز است | درخواست Ubuntu؛ اجرای Docker روی Windows Server برای این پروژه توصیه نمی‌شود |
| سرور OpenVZ/LXC | درخواست VM با KVM |
| فقط آی‌پی (بدون دامنه) | HTTP + رمز؛ ترجیحاً پشت VPN/فایروال؛ برای HTTPS دامنه لازم است |
| دیسک پر شود | `JUDGE_RETENTION_DAYS` را کم کن |
| آنالیز کند باشد | `JUDGE_WORKERS` را متناسب با CPU/RAM تنظیم کن؛ `JUDGE_FPS=15` را نگه دار |
