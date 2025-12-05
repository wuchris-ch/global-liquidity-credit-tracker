import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import { SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryProvider } from "@/components/query-provider";

export const metadata: Metadata = {
  title: "Global Liquidity Tracker",
  description: "Central bank liquidity, credit conditions & funding stress",
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
    <html lang="en" className="dark">
      <head>
        {/* Critical mobile styles - loaded before any JS */}
        <style dangerouslySetInnerHTML={{ __html: `
          @media (max-width: 767px) {
            .mobile-main-wrapper {
              position: fixed !important;
              top: 0 !important;
              left: 0 !important;
              right: 0 !important;
              bottom: 0 !important;
              width: 100vw !important;
              height: 100dvh !important;
              overflow-y: auto !important;
              overflow-x: hidden !important;
              z-index: 1 !important;
            }
            [data-slot="sidebar-gap"] { display: none !important; }
          }
        `}} />
      </head>
      <body className={`${GeistSans.variable} ${GeistMono.variable} font-sans antialiased overflow-x-hidden`}>
        <QueryProvider>
          <TooltipProvider delayDuration={0}>
            <SidebarProvider defaultOpen={true}>
              <AppSidebar />
              {/* Mobile wrapper ensures full width regardless of sidebar state */}
              <div className="mobile-main-wrapper">
                <main className="flex-1 overflow-x-hidden overflow-y-auto w-full max-w-full">
                  {children}
                </main>
              </div>
            </SidebarProvider>
          </TooltipProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
