"use client";

import { Dumbbell, Sun, Moon, Languages } from "lucide-react";
import { useTheme } from "next-themes";
import { useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** v1 template header + the two user toggles (theme, language). */
export function Header() {
  const { t, lang, setLang } = useLang();
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <header className="sticky top-0 z-50 border-b border-edge bg-app/80 backdrop-blur-sm">
      <div className="mx-auto max-w-7xl w-full px-4 sm:px-6 py-3.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-red-500 to-orange-600 shadow-lg shadow-red-500/20">
            <Dumbbell className="h-4.5 w-4.5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-ink leading-none">
              CrossFit Judge
            </h1>
            <p className="text-[11px] text-ink-3 mt-0.5">{t("header.subtitle")}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="hidden sm:flex items-center gap-2 text-xs text-ink-3">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            {t("header.engineOnline")}
          </span>

          {/* language: EN (default) | FA */}
          <div
            role="group"
            aria-label={t("header.langAria")}
            title={t("header.langAria")}
            className="flex items-center gap-0.5 rounded-lg border border-edge bg-panel p-0.5"
          >
            <Languages className="h-3.5 w-3.5 text-ink-3 ms-1" aria-hidden />
            {(["en", "fa"] as const).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                aria-pressed={lang === l}
                className={cn(
                  "rounded-md px-2 py-1 text-[11px] font-bold transition-all",
                  lang === l
                    ? "bg-brand text-white"
                    : "text-ink-3 hover:text-ink-2",
                )}
              >
                {l === "en" ? "EN" : "فا"}
              </button>
            ))}
          </div>

          {/* theme: light / dark */}
          <button
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            aria-label={t("header.themeAria")}
            title={t("header.themeAria")}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-edge text-ink-2 transition-colors hover:border-edge-2 hover:text-ink"
          >
            <Sun className="h-4 w-4 hidden dark:block" />
            <Moon className="h-4 w-4 dark:hidden" />
          </button>
        </div>
      </div>
    </header>
  );
}
