import type { Metadata } from "next";
import "./globals.css";

const themeScript = `(function(){try{var t=localStorage.getItem("regora-theme");document.documentElement.dataset.theme=t==="light"||t==="amoled"||t==="dark"?t:"dark"}catch(e){document.documentElement.dataset.theme="dark"}})()`;

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
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
