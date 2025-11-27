import type { Metadata } from "next";
import { Sora, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryProvider } from "@/components/query-provider";

const sora = Sora({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Global Liquidity Tracker",
  description: "Central bank liquidity, credit conditions & funding stress",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${sora.variable} ${ibmPlexMono.variable} font-sans`}>
        <QueryProvider>
          <TooltipProvider delayDuration={0}>
            <SidebarProvider defaultOpen={true}>
              <AppSidebar />
              <main className="flex-1 overflow-auto">
                {children}
              </main>
            </SidebarProvider>
          </TooltipProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
