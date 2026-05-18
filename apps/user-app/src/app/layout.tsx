import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { AuthGuard } from "@auto-at/shared";
import { TopNav } from "@/components/layout/TopNav";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: {
    default: "Auto-AT – Run Pipelines",
    template: "%s | Auto-AT",
  },
  description:
    "End-user portal for running AI test pipelines. Pick a template, run it, watch progress in real-time.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased min-h-dvh flex flex-col bg-[#101622] text-white">
        <Providers>
          <AuthGuard>
            <TopNav />
            <main className="flex-1">{children}</main>
          </AuthGuard>
        </Providers>
      </body>
    </html>
  );
}
