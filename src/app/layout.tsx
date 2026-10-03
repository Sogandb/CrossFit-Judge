import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { ThemeProvider } from "@/components/theme-provider";
import { LangProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "CrossFit Judge — AI Competition Judge",
  description:
    "Automated CrossFit competition judging using MediaPipe Pose and OpenCV. Detects movements, counts valid reps, and scores athletes according to CrossFit Games standards.",
  keywords: [
    "CrossFit",
    "AI Judge",
    "MediaPipe",
    "Pose Detection",
    "Competition",
    "OpenCV",
  ],
  authors: [{ name: "CrossFit Judge" }],
  openGraph: {
    title: "CrossFit Judge — AI Competition Judge",
    description:
      "Automated CrossFit competition judging using pose detection",
    type: "website",
  },
};

// Pre-paint language/dir bootstrap (theme class is handled by next-themes).
const langInit = `try{var l=localStorage.getItem("cfj-lang")||"en";var d=document.documentElement;d.lang=l;d.dir=l==="fa"?"rtl":"ltr";}catch(e){}`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: langInit }} />
      </head>
      <body className="font-sans antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <LangProvider>{children}</LangProvider>
        </ThemeProvider>
        <Toaster />
      </body>
    </html>
  );
}
