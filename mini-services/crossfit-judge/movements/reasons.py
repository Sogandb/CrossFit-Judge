"""
No-rep / review-flag reason registry — SINGLE SOURCE OF TRUTH for all
user-facing reason strings (fixes the v1 fa/en field-swap bug by design).

Categories:
  NO_REP    → automatic no-rep (high-confidence vision signal)
  REVIEW    → human-review flag (lower-confidence signal; asymmetric error
              policy: never auto-penalise when unsure)
  INFO      → informational notes in the log.
"""
from __future__ import annotations

REASONS: dict[str, dict] = {
    # ----------------------------- THRUSTER -------------------------------- #
    "THR_DEPTH": {
        "category": "NO_REP",
        "fa": "عمق اسکوات کافی نبود — چین لگن پایین‌تر از سطح بالای زانو نرفت",
        "en": "Insufficient squat depth — hip crease did not pass below the knee line",
    },
    "THR_LOCKOUT": {
        "category": "NO_REP",
        "fa": "قفل کامل در بخش بالایی حرکت انجام نشد (لگن، زانو یا آرنج‌ها کاملاً باز نشدند)",
        "en": "Incomplete lockout — hips, knees or elbows not fully extended overhead",
    },
    "THR_BAR_NOT_OVERHEAD": {
        "category": "NO_REP",
        "fa": "میله در وضعیت بالای سر (وسط بدن یا پشت آن) قرار نگرفت",
        "en": "Bar did not reach the overhead position (mid-line or behind)",
    },
    "THR_NOT_CONTINUOUS": {
        "category": "NO_REP",
        "fa": "تراستر یک حرکت پیوسته است — اسکوات کامل، توقف و سپس جرک مجاز نیست",
        "en": "Not continuous — full front squat, pause, then jerk is not a thruster",
    },
    "THR_WALKING": {
        "category": "NO_REP",
        "fa": "قدم زدن رو به جلو در حین اجرای حرکت — خطا",
        "en": "Walking forward during the movement is a fault",
    },
    # ---- borderline bands (credited, flagged for human review) ---- #
    "THR_DEPTH_REVIEW": {
        "category": "REVIEW",
        "fa": "عمق اسکوات در حد مرز بود (چین لگن تقریباً هم‌سطح زانو) — به نفع ورزشکار شمرده شد؛ بازبینی توصیه می‌شود",
        "en": "Squat depth was borderline (hip crease near the knee line) — credited to the athlete; review recommended",
    },
    "THR_LOCKOUT_REVIEW": {
        "category": "REVIEW",
        "fa": "کامل بودن قفل بالای حرکت از روی تصویر قابل اطمینان نبود — به نفع ورزشکار شمرده شد؛ بازبینی توصیه می‌شود",
        "en": "Full overhead lockout could not be confirmed from the footage — credited to the athlete; review recommended",
    },
    "THR_WALKING_REVIEW": {
        "category": "REVIEW",
        "fa": "جابه‌جایی پاها در حین رپ دیده شد اما آشکارا قدم برداشتن نبود (بازبینی)",
        "en": "Some foot movement seen during the rep but not clearly walking (review)",
    },
    "THR_RACK_ELBOWS": {
        "category": "REVIEW",
        "fa": "وضعیت رک مشکوک است — آرنج‌ها باید جلوی میله باشند (نیازمند بازبینی)",
        "en": "Rack position questionable — elbows must stay in front of the bar (review)",
    },
    "THR_BAR_LINE": {
        "category": "REVIEW",
        "fa": "میله در قفل، خارج از راستای وسط بدن به نظر می‌رسد (نیازمند بازبینی)",
        "en": "At lockout the bar appears outside the mid-line of the body (review)",
    },
    "THR_HANDS_TO_LEG": {
        "category": "REVIEW",
        "fa": "احتمال برخورد یا تکیه دست‌ها به پاها در حین حرکت (نیازمند بازبینی)",
        "en": "Possible hands-to-legs contact during the movement (review)",
    },
    "THR_LOW_VIS": {
        "category": "REVIEW",
        "fa": "کیفیت تشخیص نقاط بدن در این رپ پایین بود — قابل تأیید خودکار نیست",
        "en": "Landmark visibility too low for this rep — not auto-judgeable (review)",
    },
    # ------------------------- BAR-FACING BURPEE --------------------------- #
    "BFB_CHEST": {
        "category": "NO_REP",
        "fa": "سینه (قفسه سینه) زمین را لمس نکرد",
        "en": "Sternum did not touch the ground",
    },
    "BFB_NOT_FACING": {
        "category": "NO_REP",
        "fa": "ورزشکار هنگام شروع رپ روبروی بار نبود (موازی بار ایستاده بود)",
        "en": "Athlete was parallel to (not facing) the bar at rep start",
    },
    "BFB_ONE_FOOT_LANDING": {
        "category": "NO_REP",
        "fa": "فرود باید همزمان با هر دو پا انجام شود — فرود تک‌پا مجاز نیست",
        "en": "Landing must be simultaneous on both feet — one-foot landing is a fault",
    },
    "BFB_TRAILING_FOOT": {
        "category": "NO_REP",
        "fa": "پای عقب روی زمین و این‌طرف بار باقی ماند در لحظه عبور پای جلو (شرط پرش تک‌پا رعایت نشد)",
        "en": "Trailing foot stayed grounded on the start side while the lead foot crossed",
    },
    "BFB_INCOMPLETE_CROSS": {
        "category": "NO_REP",
        "fa": "عبور کامل از بار انجام نشد — هر دو پا باید از آن‌طرف بار فرود بیایند",
        "en": "Incomplete crossing — both feet must land beyond the bar",
    },
    "BFB_NO_JUMP": {
        "category": "NO_REP",
        "fa": "عبور از بار باید با پرش باشد — عبور قدمی مجاز نیست",
        "en": "The bar must be cleared with a jump — stepping over is not allowed",
    },
    # ---- borderline bands (credited, flagged for human review) ---- #
    "BFB_CHEST_REVIEW": {
        "category": "REVIEW",
        "fa": "لمس سینه زمین به‌طور قطعی قابل تأیید نبود — به نفع ورزشکار شمرده شد؛ بازبینی توصیه می‌شود",
        "en": "Chest-to-ground contact could not be conclusively confirmed — credited to the athlete; review recommended",
    },
    "BFB_FACING_REVIEW": {
        "category": "REVIEW",
        "fa": "زاویه دوربین اجازه تأیید قطعی رو به بار بودن را نداد (بازبینی)",
        "en": "Camera angle does not allow conclusive facing verification (review)",
    },
    "BFB_CROSS_REVIEW": {
        "category": "REVIEW",
        "fa": "عبور از بار در حد مرز بود — به نفع ورزشکار شمرده شد؛ بازبینی توصیه می‌شود",
        "en": "Bar crossing was borderline — credited to the athlete; review recommended",
    },
    "BFB_LANDING_REVIEW": {
        "category": "REVIEW",
        "fa": "همزمانی فرود دو پا در حد مرز بود — به نفع ورزشکار شمرده شد (بازبینی)",
        "en": "Two-foot landing simultaneity was borderline — credited to the athlete (review)",
    },
    "BFB_JUMP_REVIEW": {
        "category": "REVIEW",
        "fa": "پرش بودن عبور از بار به‌طور قطعی قابل تأیید نبود — به نفع ورزشکار شمرده شد (بازبینی)",
        "en": "The jump over the bar could not be conclusively verified — credited to the athlete (review)",
    },
    "BFB_BAR_CONTACT": {
        "category": "REVIEW",
        "fa": "احتمال تماس پا یا بدن با بار در حین پرش (نیازمند بازبینی)",
        "en": "Possible contact with the bar during the jump (review)",
    },
    "BFB_LOW_VIS": {
        "category": "REVIEW",
        "fa": "کیفیت تشخیص نقاط بدن در این رپ پایین بود — قابل تأیید خودکار نیست",
        "en": "Landmark visibility too low for this rep — not auto-judgeable (review)",
    },
    # ------------------------------ SYSTEM --------------------------------- #
    "SYS_START_NOT_FOUND": {
        "category": "INFO",
        "fa": "الگوی بوق شروع (۳+۱) شناسایی نشد — تحلیل از ابتدای ویدیو انجام شد؛ زمان‌ها ممکن است شامل زمان آماده‌سازی باشند",
        "en": "Start beep pattern (3+1) not found — analyzed from video start; times may include setup",
    },
    "SYS_BAR_ANCHOR_LOW_CONF": {
        "category": "INFO",
        "fa": "موقعیت میله با اطمینان پایین تخمین خورد — معیارهای عبور با دقت کمتر اعمال شد",
        "en": "Bar position estimated with low confidence — crossing checks were degraded",
    },
    "SYS_NO_PERSON": {
        "category": "INFO",
        "fa": "در بخش قابل‌توجهی از ویدیو ورزشکار شناسایی نشد — کیفیت تصویر/زاویه دوربین را بررسی کنید",
        "en": "No athlete detected for a large portion of the video — check framing/camera angle",
    },
    # --------------------------- SEQUENCER ---------------------------------- #
    "SEQ_BLOCK_INCOMPLETE": {
        "category": "REVIEW",
        "fa": "رند ناقص به نظر می‌رسد — تعدادی رپ شناسایی‌نشده یا کم‌شمار وجود دارد",
        "en": "Block appears incomplete — some reps were missed or under-counted",
    },
    "SEQ_EXCESS_REPS": {
        "category": "REVIEW",
        "fa": "رپ‌های اضافه بیش از تعداد تعیین‌شده این رند انجام شد (در امتیاز منظور نشد)",
        "en": "More reps performed than prescribed for this block (excess not scored)",
    },
    "SEQ_ORDER_DEVIATION": {
        "category": "REVIEW",
        "fa": "توالی حرکات با ترتیب واد مطابقت نداشت — بازبینی توصیه می‌شود",
        "en": "Movement order deviated from the prescribed WOD sequence — review recommended",
    },
    "SEQ_MOVEMENT_MISMATCH": {
        "category": "REVIEW",
        "fa": "این تلاش مربوط به حرکتی است که در این نقطه از واد منتظر نبود — شمرده نشد",
        "en": "This attempt was of a movement not expected at this point of the WOD — not counted",
    },
    "SEQ_REALIGN_BACKWARD": {
        "category": "REVIEW",
        "fa": "سیستم توالی را با موقعیت واقعی ورزشکار هم‌راستا کرد (رندی که پیش‌تر ناقص مانده بود) — بازبینی توصیه می‌شود",
        "en": "The engine re-aligned the sequence with the athlete's actual position (an earlier block was still incomplete) — review recommended",
    },
    "SEQ_SAME_MOVE_FLOW": {
        "category": "REVIEW",
        "fa": "ورزشکار همین حرکت را ادامه داد و رپ‌ها در رند بعدیِ همان حرکت منظور شد — بازبینی ترتیب توصیه می‌شود",
        "en": "The athlete continued the same movement — reps were credited to the next round of that movement; order review recommended",
    },
}


def reason(code: str) -> dict:
    if code not in REASONS:
        raise KeyError(f"Unknown reason code: {code}")
    return REASONS[code]


def reason_fa(code: str) -> str:
    return reason(code)["fa"]


def reason_en(code: str) -> str:
    return reason(code)["en"]


def reason_category(code: str) -> str:
    return reason(code)["category"]
