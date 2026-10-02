import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

export const metadata: Metadata = {
  title: "داور هوشمند کراس‌فیت — نسخه ۲",
  description:
    "سیستم دستیار داوری مسابقات آنلاین کراس‌فیت با تحلیل ویدیو و شمارش هوشمند رپ — نمونه اولیه برای پلتفرم وادکس",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fa" dir="rtl" suppressHydrationWarning>
      <body className="font-sans antialiased">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
