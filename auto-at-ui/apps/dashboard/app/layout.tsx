import type { ReactNode } from "react";
import { AppShell } from "./components/app-shell";
import "./globals.css";

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="en"><body><AppShell>{children}</AppShell></body></html>;
}
