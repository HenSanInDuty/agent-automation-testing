import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { AuthGuard } from "@/components/auth/AuthGuard";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: {
    default: "Auto-AT Admin – Pipeline Management",
    template: "%s | Auto-AT Admin",
  },
  description:
    "Admin console: manage pipeline templates, LLM profiles, agent configs, and users.",
  keywords: ["automation", "testing", "AI", "multi-agent", "CrewAI"],
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
        <Providers><AuthGuard>{children}</AuthGuard></Providers>
      </body>
    </html>
  );
}
