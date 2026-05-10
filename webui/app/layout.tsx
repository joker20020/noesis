import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Noesis",
  description: "Self-evolving Agent Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="bg-zinc-950 text-zinc-100 min-h-screen">{children}</body>
    </html>
  );
}
