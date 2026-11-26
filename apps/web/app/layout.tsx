import type { Metadata } from "next";
import "./globals.css";
import { LocaleProvider } from "./i18n";

export const metadata: Metadata = {
  title: "Doctor Matching Agent",
  description: "Doctor Matching Agent MVP foundation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant">
      <body><LocaleProvider>{children}</LocaleProvider></body>
    </html>
  );
}

