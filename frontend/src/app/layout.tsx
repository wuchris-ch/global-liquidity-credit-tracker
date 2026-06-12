import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Newsreader } from "next/font/google";
import "./globals.css";
import { Masthead } from "@/components/masthead";
import { QueryProvider } from "@/components/query-provider";

const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-newsreader",
});

export const metadata: Metadata = {
  title: "Global Liquidity & Credit",
  description:
    "A daily read on global liquidity and credit conditions: regime, drivers, and what it has meant for assets.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  minimumScale: 1,
  maximumScale: 5,
  userScalable: true,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${GeistSans.variable} ${GeistMono.variable} ${newsreader.variable} font-sans antialiased`}
      >
        <QueryProvider>
          <div className="flex min-h-screen flex-col">
            <Masthead />
            <main className="flex-1">{children}</main>
            <footer className="border-t border-border">
              <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-8">
                <p className="font-mono text-xs text-muted-foreground">
                  Sources: FRED, BIS, World Bank, NY Fed, Yahoo Finance. Updated twice daily.
                  Not investment advice.
                </p>
              </div>
            </footer>
          </div>
        </QueryProvider>
      </body>
    </html>
  );
}
