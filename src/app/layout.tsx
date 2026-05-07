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
  title: "Working Capital Optimizer — AI Agent Mesh for CFO Intelligence",
  description: "Multi-agent AI system that monitors AR, AP, inventory and cash flow to recommend specific actions that shrink the cash conversion cycle. Traced and self-improving via Arize Phoenix.",
  keywords: ["working capital", "AI agents", "Gemini", "Arize Phoenix", "cash conversion cycle", "CFO", "manufacturing", "OpenInference"],
  authors: [{ name: "cubiczan" }],
  openGraph: {
    title: "Working Capital Optimizer",
    description: "AI agent mesh for CFO-level working capital intelligence",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Working Capital Optimizer",
    description: "AI agent mesh for CFO-level working capital intelligence",
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
