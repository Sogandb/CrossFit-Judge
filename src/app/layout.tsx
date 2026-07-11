import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

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

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
