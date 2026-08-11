import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { themeBootstrapScript } from "@/lib/theme";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Ergonomia AI — analiza ergonomii na podstawie filmu",
    template: "%s | Ergonomia AI",
  },
  description:
    "Analiza ruchu, metryki postawy i raport ergonomiczny na podstawie krótkiego nagrania.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="pl"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      data-theme="light"
      suppressHydrationWarning
    >
      <head><script dangerouslySetInnerHTML={{ __html: themeBootstrapScript() }} /></head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
