"use client";

/**
 * UI language context — English is the DEFAULT; Persian is opt-in.
 *
 * Per product decision (user rule):
 *   - UI chrome (headings, buttons, labels, toasts)  → EN / FA (this dict)
 *   - Movement names, WOD content, standards, divisions, terminology
 *     → ALWAYS ENGLISH (no translation)
 *   - No-rep REASONS                                 → ALWAYS PERSIAN
 *     (engine reason_fa is the single source of truth)
 */
import {
  createContext, useCallback, useContext, useEffect, useState,
} from "react";
import type { ReactNode } from "react";

export type Lang = "en" | "fa";

const FA_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

/** Movement display names — English in BOTH languages (product rule). */
export const MOVEMENT_LABELS: Record<string, string> = {
  thruster: "Thruster",
  bar_facing_burpee: "Bar-Facing Burpee",
};

type Entry = { en: string; fa: string };

export const DICT: Record<string, Entry> = {
  // ---------- header / footer ---------- //
  "header.subtitle": { en: "Automated competition judging", fa: "داوری خودکار مسابقات" },
  "header.engineOnline": { en: "Engine online", fa: "موتور آنلاین" },
  "header.langAria": { en: "Interface language", fa: "زبان رابط کاربری" },
  "header.themeAria": { en: "Toggle light / dark theme", fa: "تغییر تم روشن / تیره" },

  // ---------- sidebar ---------- //
  "side.workflow": { en: "Workflow", fa: "روند کار" },
  "side.step1": { en: "Workout & Upload", fa: "واد و ارسال" },
  "side.step2": { en: "Analyze", fa: "تحلیل" },
  "side.step3": { en: "Review Results", fa: "بازبینی نتیجه" },
  "side.workout": { en: "Workout", fa: "واد" },
  "side.totalReps": { en: "126 total reps", fa: "مجموع ۱۲۶ رپ" },
  "side.recent": { en: "Recent Analyses", fa: "تحلیل‌های اخیر" },
  "side.recentEmpty": { en: "No analyses yet", fa: "هنوز تحلیلی ثبت نشده است" },
  "side.noteTitle": { en: "Judging Note", fa: "نکته داوری" },
  "side.noteBody": {
    en: "The engine is calibrated for this WOD's movements (Thruster and Bar-Facing Burpee). Ambiguous reps are never silently dropped — they are flagged for a human judge.",
    fa: "دقت سیستم روی حرکات این واد (Thruster و Bar-Facing Burpee) کالیبره شده است. رپ‌های مبهم به‌جای حذف، با برچسب بازبینی به داور انسانی ارجاع می‌شوند.",
  },

  // ---------- main headings ---------- //
  "main.workoutTitle": { en: "Competition Workout", fa: "واد مسابقه" },
  "main.workoutSub": {
    en: "Review the movement standards, then upload your video together with your claimed score.",
    fa: "استانداردهای حرکت را بخوانید، سپس ویدیوی خود را همراه با امتیاز ادعایی ارسال کنید.",
  },

  // ---------- workout card ---------- //
  "wod.timeCap": { en: "10 min cap", fa: "محدودیت ۱۰ دقیقه" },
  "wod.scoring": { en: "Scoring", fa: "امتیازدهی" },
  "wod.standardsThruster": { en: "Movement Standards — Thruster", fa: "استاندارد حرکت — Thruster" },
  "wod.standardsBfb": { en: "Movement Standards — Bar-Facing Burpee", fa: "استاندارد حرکت — Bar-Facing Burpee" },

  // ---------- upload form ---------- //
  "form.uploadTitle": { en: "Upload Your Video", fa: "ارسال ویدیوی شما" },
  "form.dropHere": { en: "Drop your video here, or click to browse", fa: "ویدیو را اینجا رها کنید یا کلیک کنید" },
  "form.dropHint": { en: "MP4 / MOV / WebM — max 15 minutes — 45° camera angle recommended", fa: "MP4 / MOV / WebM — حداکثر ۱۵ دقیقه — زاویه ۴۵ درجه توصیه می‌شود" },
  "form.fileReady": { en: "MB — ready for analysis", fa: "مگابایت — آماده تحلیل" },
  "form.remove": { en: "Remove", fa: "حذف" },
  "form.division": { en: "Division", fa: "رده سنی / جنسیت" },
  "form.divisionPlaceholder": { en: "Select your division", fa: "رده خود را انتخاب کنید" },
  "form.weightsNote": {
    en: "Bar weights are placeholders pending official Wodx confirmation.",
    fa: "وزن میله‌ها پیش‌فرض است و منتظر تأیید رسمی وادکس.",
  },
  "form.athlete": { en: "Athlete name (optional)", fa: "نام ورزشکار (اختیاری)" },
  "form.athletePlaceholder": { en: "e.g. Ali Rezaei", fa: "مثلاً: علی رضایی" },
  "form.claimedReps": { en: "Reps I counted myself", fa: "رپ‌های شمرده‌شده توسط خودم" },
  "form.claimedRepsPlaceholder": { en: "e.g. 126", fa: "مثلاً: 126" },
  "form.timeClaim": { en: "My time status", fa: "وضعیت زمانی من" },
  "form.timeFinished": { en: "Finished under the time cap — my time:", fa: "وادی را زیر زمان مجاز تمام کردم — زمان من:" },
  "form.timeCapped": { en: "Did not finish within the cap (capped)", fa: "در زمان مجاز تمام نشد (کپ)" },
  "form.timeNone": { en: "Prefer not to say", fa: "فعلاً نمی‌گویم" },
  "form.minutes": { en: "min", fa: "دقیقه" },
  "form.seconds": { en: "sec", fa: "ثانیه" },
  "form.manualStart": { en: "Workout start moment in the video (optional)", fa: "لحظه شروع وادی در ویدیو (اختیاری)" },
  "form.manualStartHint": {
    en: "Leave empty and the system will detect the 3+1 timer beeps automatically.",
    fa: "اگر خالی بماند، سیستم با تشخیص بوق ۳+۱ تایمر، لحظه شروع را پیدا می‌کند.",
  },
  "form.start": { en: "Start Analysis", fa: "شروع تحلیل" },
  "form.submitting": { en: "Submitting…", fa: "در حال ارسال…" },
  "form.errFile": { en: "Please choose a video file (MP4 / MOV / WebM).", fa: "فایل ویدیو را انتخاب کنید (MP4 / MOV / WebM)." },
  "form.errDivision": { en: "Please select your division.", fa: "رده سنی را انتخاب کنید." },
  "form.errReps": { en: "Claimed rep count is not valid (0–126).", fa: "تعداد رپ ادعایی نامعتبر است (۰ تا ۱۲۶)." },
  "form.errTime": { en: "Please enter your claimed finish time correctly.", fa: "زمان ادعایی را درست وارد کنید." },
  "form.errManualStart": { en: "Start moment (seconds) is not valid.", fa: "لحظه شروع (ثانیه) نامعتبر است." },
  "form.uploadFailed": { en: "Upload failed", fa: "خطا در ارسال" },
  "form.connecting": { en: "Connecting to the analysis service…", fa: "در حال اتصال به سرویس تحلیل…" },
  "form.serviceDown": { en: "Analysis service unavailable", fa: "سرویس تحلیل در دسترس نیست" },
  "form.uploadReceived": { en: "Video received", fa: "ویدیو دریافت شد" },
  "form.uploadStarted": { en: "Analysis started — keep this page open.", fa: "تحلیل آغاز شد — این صفحه را باز نگه دارید." },

  // ---------- processing ---------- //
  "proc.uploading": { en: "Uploading Video", fa: "در حال ارسال ویدیو" },
  "proc.analyzing": { en: "Analyzing Movement", fa: "در حال تحلیل حرکت" },
  "proc.uploadSub": { en: "Sending your video to the judge engine", fa: "ویدیو به موتور داوری ارسال می‌شود" },
  "proc.defaultMsg": { en: "Running pose detection & rep counting", fa: "اجرای تشخیص حرکت و شمارش رپ" },
  "proc.cancel": { en: "Cancel", fa: "لغو" },
  "proc.uploadingLabel": { en: "Uploading…", fa: "در حال ارسال…" },
  "proc.hint": {
    en: "A 12–15 minute video takes a few minutes on a typical server. This page updates automatically.",
    fa: "تحلیل یک ویدیوی ۱۲ تا ۱۵ دقیقه‌ای روی سرور معمولی چند دقیقه طول می‌کشد؛ این صفحه خودکار به‌روز می‌شود.",
  },
  "proc.cancelled": { en: "Upload cancelled — the analysis form is back.", fa: "ارسال لغو شد — فرم تحلیل برگشت." },
  "stage.queued": { en: "Queued", fa: "صف" },
  "stage.validate": { en: "Validate", fa: "اعتبارسنجی" },
  "stage.start_detect": { en: "Start", fa: "شروع" },
  "stage.analyzing": { en: "Frames", fa: "فریم‌ها" },
  "stage.scoring": { en: "Score", fa: "امتیاز" },
  "stage.done": { en: "Ready", fa: "آماده" },

  // ---------- failure ---------- //
  "fail.title": { en: "Analysis Failed", fa: "تحلیل ناموفق بود" },
  "fail.fallback": { en: "An unexpected error occurred.", fa: "خطای غیرمنتظره رخ داد." },
  "fail.lostConnection": {
    en: "Lost connection to the analysis server — it may still be processing. Check Recent Analyses and reopen it later.",
    fa: "اتصال به سرور تحلیل قطع شد — ممکن است پردازش همچنان در جریان باشد. از تحلیل‌های اخیر دوباره بازش کنید.",
  },
  "fail.startOver": { en: "Start Over", fa: "شروع دوباره" },

  // ---------- results ---------- //
  "res.title": { en: "Judging Results", fa: "نتیجه داوری" },
  "res.new": { en: "New Analysis", fa: "تحلیل جدید" },
  "res.finalScore": { en: "Final Score", fa: "امتیاز نهایی" },
  "res.forTime": { en: "For Time", fa: "For Time" },
  "res.finished": { en: "Finished", fa: "کامل شد" },
  "res.validReps": { en: "Valid Reps", fa: "رپ‌های تأییدشده" },
  "res.time": { en: "Time", fa: "زمان" },
  "res.noReps": { en: "No-Reps", fa: "نو-رپ" },
  "res.noRepShort": { en: "no-rep", fa: "نو-رپ" },
  "res.prescribed": { en: "Prescribed", fa: "تعیین‌شده" },
  "res.capStatus": { en: "Capped", fa: "کپ" },
  "res.ofReps": { en: "reps", fa: "رپ" },
  "res.athlete": { en: "Athlete", fa: "ورزشکار" },
  "res.analysisId": { en: "Analysis ID", fa: "شناسه تحلیل" },
  "res.startDetection": { en: "Start Detection", fa: "تشخیص شروع" },
  "res.startBeep": { en: "3+1 timer beeps", fa: "بوق ۳+۱ تایمر" },
  "res.startManual": { en: "Manual", fa: "دستی" },
  "res.startMock": { en: "Demo mode", fa: "حالت نمایشی" },
  "res.startVideo": { en: "Video start (beeps not found)", fa: "ابتدای ویدیو (بوق پیدا نشد)" },
  "res.startAt": { en: "Workout starts at", fa: "لحظه شروع" },
  "res.recon": { en: "Claimed-Score Reconciliation", fa: "تطبیق با امتیاز ادعایی" },
  "res.claimedReps": { en: "Claimed", fa: "ادعا" },
  "res.systemCount": { en: "System count", fa: "شمارش سیستم" },
  "res.claimedTime": { en: "Claimed time", fa: "زمان ادعایی" },
  "res.systemTime": { en: "System time", fa: "زمان سیستم" },
  "res.perMovement": { en: "Per-Movement Breakdown", fa: "تفکیک بر اساس حرکت" },
  "res.roundByRound": { en: "Round by Round", fa: "روند رندبه‌رند واد" },
  "res.round": { en: "Round", fa: "رند" },
  "res.movement": { en: "Movement", fa: "حرکت" },
  "res.status": { en: "Status", fa: "وضعیت" },
  "res.credited": { en: "Credited", fa: "تأییدشده" },
  "res.reviewOutput": { en: "Review Output", fa: "خروجی بازبینی" },
  "res.reviewHint": {
    en: "Annotated with skeleton overlay, live rep counter and workout clock. Click any row in the breakdown to jump to that moment.",
    fa: "ویدیو با اسکلت، شمارنده رپ و ساعت واد نشانه‌گذاری شده است. روی هر ردیف از جدول کلیک کنید تا به همان لحظه بروید.",
  },
  "res.repTable": { en: "Rep-by-Rep Breakdown", fa: "تفکیک رپ به رپ" },
  "res.attempts": { en: "total attempts", fa: "تلاش" },
  "res.reasonInPersian": { en: "no-rep reasons shown in Persian", fa: "دلایل نو-رپ" },
  "res.verdictGood": { en: "Good", fa: "تأیید" },
  "res.verdictNoRep": { en: "No-Rep", fa: "نو-رپ" },
  "res.verdict": { en: "Verdict", fa: "رأی" },
  "res.postCap": { en: "Post-Cap", fa: "بعد از کپ" },
  "res.needReview": { en: "Review", fa: "بازبینی" },
  "res.reason": { en: "Reason", fa: "دلیل" },
  "res.noEvents": { en: "No reps were detected in this video.", fa: "هیچ رپی در این ویدیو شناسایی نشد." },
  "res.noEventsHint": {
    en: "Make sure the athlete is fully visible from a 45° angle.",
    fa: "مطمئن شوید ورزشکار از زاویه ۴۵ درجه به‌طور کامل دیده می‌شود.",
  },
  "res.flaggedTitle": { en: "Flagged for Human Judge Review", fa: "موارد ارجاع به بازبینی داور انسانی" },
  "res.downloadJson": { en: "Download Full Report (JSON)", fa: "دانلود گزارش کامل (JSON)" },
  "res.disclaimer": {
    en: "System output is a recommendation for the judge; the final decision stays with human review.",
    fa: "خروجی سیستم توصیه‌ای برای داور است؛ تصمیم نهایی داوری با بازبینی انسانی است.",
  },
};

interface LangCtx {
  lang: Lang;
  dir: "ltr" | "rtl";
  setLang: (l: Lang) => void;
  t: (key: string) => string;
  /** Localized digits (Latin in EN, Persian in FA). */
  n: (v: number | string) => string;
  /** mm:ss clock with localized digits. */
  clock: (sec: number | null | undefined) => string;
  /** Locale-aware date-time. */
  dateTime: (epochSec: number) => string;
}

const Ctx = createContext<LangCtx | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  // restore saved preference (the pre-paint script already set <html> attrs).
  // Deferred to a callback so the effect body itself stays render-free.
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem("cfj-lang"); } catch { /* ignore */ }
    if (saved === "fa") {
      const id = requestAnimationFrame(() => setLangState("fa"));
      return () => cancelAnimationFrame(id);
    }
  }, []);

  useEffect(() => {
    const el = document.documentElement;
    el.lang = lang;
    el.dir = lang === "fa" ? "rtl" : "ltr";
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { localStorage.setItem("cfj-lang", l); } catch { /* ignore */ }
  }, []);

  const t = useCallback(
    (key: string) => DICT[key]?.[lang] ?? key,
    [lang],
  );

  const n = useCallback(
    (v: number | string) =>
      lang === "fa"
        ? String(v).replace(/[0-9]/g, (d) => FA_DIGITS[Number(d)])
        : String(v),
    [lang],
  );

  const clock = useCallback(
    (sec: number | null | undefined) => {
      if (sec == null || !isFinite(sec)) return "—";
      const neg = sec < 0;
      const s = Math.abs(Math.round(sec));
      const mm = String(Math.floor(s / 60)).padStart(2, "0");
      const ss = String(s % 60).padStart(2, "0");
      return (neg ? "−" : "") + n(`${mm}:${ss}`);
    },
    [n],
  );

  const dateTime = useCallback(
    (epochSec: number) => {
      try {
        return new Intl.DateTimeFormat(lang === "fa" ? "fa-IR" : "en-US", {
          dateStyle: "medium", timeStyle: "short",
        }).format(new Date(epochSec * 1000));
      } catch {
        return "—";
      }
    },
    [lang],
  );

  return (
    <Ctx.Provider value={{
      lang,
      dir: lang === "fa" ? "rtl" : "ltr",
      setLang, t, n, clock, dateTime,
    }}>
      {children}
    </Ctx.Provider>
  );
}

export function useLang(): LangCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useLang must be used inside <LangProvider>");
  return ctx;
}
