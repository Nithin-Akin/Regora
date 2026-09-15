import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Regora — Understand a codebase before you break it.",
  description:
    "Explore real code dependencies, trace requests, and understand change impact with evidence-backed AI.",
  icons: { icon: "/regora-mark.svg" },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
