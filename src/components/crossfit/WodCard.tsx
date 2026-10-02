"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion";
import { faClock, toFa } from "@/lib/fa";

const THRUSTER_STANDARDS: { title: string; items: string[] }[] = [
  {
    title: "شروع حرکت",
    items: [
      "هالتر باید روی زمین قرار داشته باشد",
      "استفاده از رک (Rack) برای برداشتن هالتر مجاز نیست",
      "هنگام برداشتن هالتر از روی زمین، اجرای اسکوات کلین مستقیم به تراستر مجاز است",
    ],
  },
  {
    title: "اجرای اسکوات",
    items: [
      "ورزشکار باید هالتر را در وضعیت رک (Rack Position) روی شانه‌ها قرار دهد",
      "آرنج‌ها باید جلوتر از میله باشند",
      "چین لگن باید پایین‌تر از سطح بالای زانو برود (Below Parallel)",
      "برخورد دست‌ها به پاها در طول حرکت خطا محسوب می‌شود",
    ],
  },
  {
    title: "پایان حرکت",
    items: [
      "در بخش بالایی حرکت، مفاصل لگن، زانوها و آرنج‌ها باید کاملاً باز شوند (Full Extension)",
      "هالتر باید در راستای میانی بدن یا پشت آن قرار گیرد (از زاویه بغل)",
      "هر دو پا در یک خط، زیر بدن قرار داشته باشند",
    ],
  },
  {
    title: "نکات مهم",
    items: [
      "اسکوات کامل + توقف + جرک (Push/Split/Power Jerk) دیگر تراستر محسوب نمی‌شود — حرکت باید پیوسته باشد",
      "قدم زدن رو به جلو در طول حرکت خطاست",
    ],
  },
];

const BFB_STANDARDS: { title: string; items: string[] }[] = [
  {
    title: "تبصره‌های مهم",
    items: [
      "پرش تک‌پا مجاز است: ورزشکار یک پا را بلند می‌کند و پای بعدی کمی بعد از آن در هوا دنبالش می‌رود",
      "اما اگر یک پا به آن‌طرف بار برود و فرود بیاید در حالی که پای دیگر همچنان روی زمین در نقطه شروع مانده باشد، خطاست",
      "چرخش بدن به سمت هالتر در هوا مجاز است (برای سرعت بیشتر)",
    ],
  },
  {
    title: "قوانین عمومی",
    items: [
      "ورزشکار روبروی بار بایستد (نه موازی)",
      "پاها باید نزدیک بار باشند اما روی آن نه",
      "سینه (قفسه سینه / Sternum) باید زمین را لمس کند",
      "پرش به حالت ایستاده و فرود با دو پا همزمان در آن‌طرف بار",
      "ورزشکار باید به‌طور کامل از بار عبور کند — هر دو پا فرود بیایند",
    ],
  },
  {
    title: "خطاهای رایج",
    items: [
      "نرسیدن سینه به زمین",
      "پرش یک‌پایی بدون رعایت شرط پای عقب",
      "تماس با بار در حین پرش",
    ],
  },
];

export function WodCard() {
  return (
    <Card className="border-2 border-red-600/20 shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-xl font-bold">واد تحت داوری</CardTitle>
          <Badge variant="secondary" className="bg-red-600/10 text-red-700 border border-red-600/20">
            برای زمان • محدودیت {faClock(600)}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {renderLadder()}
        </div>
        <p className="text-sm leading-7 text-muted-foreground">
          به ترتیب انجام می‌شود: {toFa(18)} تراستر سپس {toFa(18)} بورپی رو به بار، سپس
          {" "}{toFa(15)}+{toFa(15)}، {toFa(12)}+{toFa(12)}، {toFa(9)}+{toFa(9)}،
          {" "}{toFa(6)}+{toFa(6)} و {toFa(3)}+{toFa(3)}.
          مجموع {toFa(126)} رپ. اگر وادی کامل شود امتیاز «زمان پایان» است و در صورت
          اتمام زمان مجاز، «تعداد رپ‌های تأییدشده» شمرده می‌شود.
        </p>
        <Separator />
        <Accordion type="multiple" className="w-full">
          <AccordionItem value="thruster">
            <AccordionTrigger className="text-base font-bold">
              استاندارد حرکت: تراستر
            </AccordionTrigger>
            <AccordionContent className="space-y-4">
              {THRUSTER_STANDARDS.map((sec) => (
                <div key={sec.title}>
                  <h4 className="mb-1 font-semibold text-sm text-red-700">{sec.title}</h4>
                  <ul className="list-disc space-y-1 pr-5 text-sm leading-6 text-muted-foreground">
                    {sec.items.map((it) => <li key={it}>{it}</li>)}
                  </ul>
                </div>
              ))}
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="bfb">
            <AccordionTrigger className="text-base font-bold">
              استاندارد حرکت: بورپی رو به بار
            </AccordionTrigger>
            <AccordionContent className="space-y-4">
              {BFB_STANDARDS.map((sec) => (
                <div key={sec.title}>
                  <h4 className="mb-1 font-semibold text-sm text-red-700">{sec.title}</h4>
                  <ul className="list-disc space-y-1 pr-5 text-sm leading-6 text-muted-foreground">
                    {sec.items.map((it) => <li key={it}>{it}</li>)}
                  </ul>
                </div>
              ))}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
}

function renderLadder() {
  const rungs = [18, 15, 12, 9, 6, 3];
  return (
    <>
      {rungs.map((r, i) => (
        <span key={r} className="flex items-center gap-2">
          <Badge className="bg-zinc-900 text-white hover:bg-zinc-900">
            {toFa(r)} + {toFa(r)}
          </Badge>
          {i < rungs.length - 1 && <span className="text-muted-foreground">→</span>}
        </span>
      ))}
    </>
  );
}
