"use client";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import {
  Activity,
  BarChart3,
  Building2,
  Gauge,
  Globe2,
  History,
  LayoutDashboard,
  LineChart,
  PieChart,
  TrendingUp,
  Wallet,
  Clock3,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Badge } from "@/components/ui/badge";

const mainNavItems = [
  {
    title: "Dashboard",
    url: "/",
    icon: LayoutDashboard,
  },
  {
    title: "GLCI",
    url: "/glci",
    icon: Gauge,
  },
  {
    title: "Risk by Regime",
    url: "/risk",
    icon: PieChart,
  },
  {
    title: "Track Record",
    url: "/track-record",
    icon: History,
    badge: "NEW",
  },
  {
    title: "Liquidity Monitor",
    url: "/liquidity",
    icon: Activity,
  },
  {
    title: "Credit Spreads",
    url: "/spreads",
    icon: TrendingUp,
  },
  {
    title: "Data Explorer",
    url: "/explorer",
    icon: BarChart3,
  },
];

const dataSourceItems = [
  { title: "FRED", icon: Building2 },
  { title: "NY Fed", icon: Activity },
  { title: "BIS", icon: Globe2 },
  { title: "World Bank", icon: Wallet },
  { title: "Yahoo Finance", icon: LineChart },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar variant="sidebar" collapsible="icon">
      <SidebarHeader className="border-b border-sidebar-border">
        <div className="flex items-center gap-3 px-2 py-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-foreground shadow-lg">
            <Gauge className="h-5 w-5 text-background" />
          </div>
          <div className="flex flex-col group-data-[collapsible=icon]:hidden">
            <span className="text-sm font-semibold tracking-tight">Global Liquidity</span>
            <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              Tracker
            </span>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
            Navigation
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainNavItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton
                    asChild
                    isActive={pathname === item.url}
                    tooltip={item.title}
                    className="transition-all duration-200 hover:bg-accent/80"
                  >
                    <Link href={item.url}>
                      <item.icon className="h-4 w-4" />
                      <span className="font-medium">{item.title}</span>
                      {"badge" in item && item.badge && (
                        <Badge
                          variant="outline"
                          className="ml-auto h-5 border-primary/30 bg-primary/10 px-1.5 text-[9px] font-semibold uppercase tracking-wider text-primary group-data-[collapsible=icon]:hidden"
                        >
                          {item.badge}
                        </Badge>
                      )}
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
            Data Sources
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {dataSourceItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton tooltip={item.title} className="cursor-default">
                    <item.icon className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
            Data Notes
          </SidebarGroupLabel>
          <SidebarGroupContent className="px-2 group-data-[collapsible=icon]:hidden">
            <div className="space-y-3 rounded-lg bg-muted/30 p-3">
              <div className="flex items-start gap-2">
                <Clock3 className="mt-0.5 h-4 w-4 text-muted-foreground" />
                <div className="space-y-1">
                  <p className="text-xs font-medium">Scheduled publication</p>
                  <p className="text-xs text-muted-foreground">
                    Data updates on the export schedule. Each page shows the latest observation date for the data it is using.
                  </p>
                </div>
              </div>
            </div>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border">
        <div className="flex items-center gap-2 px-2 py-3 group-data-[collapsible=icon]:justify-center">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
            <LineChart className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="flex flex-col group-data-[collapsible=icon]:hidden">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Data Status
            </span>
            <span className="text-xs text-muted-foreground">See page header</span>
          </div>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}





