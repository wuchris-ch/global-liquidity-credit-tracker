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
  CircleDollarSign,
  Gauge,
  Globe2,
  LayoutDashboard,
  LineChart,
  TrendingUp,
  Wallet,
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
  { title: "FRED", icon: Building2, status: "live" },
  { title: "NY Fed", icon: CircleDollarSign, status: "live" },
  { title: "BIS", icon: Globe2, status: "live" },
  { title: "World Bank", icon: Wallet, status: "live" },
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
                    <Badge
                      variant="outline"
                      className="ml-auto h-5 border-positive/30 bg-positive/10 px-1.5 text-[9px] font-semibold uppercase tracking-wider text-positive group-data-[collapsible=icon]:hidden"
                    >
                      <span className="mr-1 h-1.5 w-1.5 rounded-full bg-positive pulse-live" />
                      {item.status}
                    </Badge>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
            Quick Stats
          </SidebarGroupLabel>
          <SidebarGroupContent className="px-2 group-data-[collapsible=icon]:hidden">
            <div className="space-y-3 rounded-lg bg-muted/30 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Fed Assets</span>
                <span className="font-mono text-xs font-semibold text-positive">$6.89T</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">SOFR Rate</span>
                <span className="font-mono text-xs font-semibold">5.31%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">HY Spread</span>
                <span className="font-mono text-xs font-semibold text-negative">+287 bps</span>
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
              Last Update
            </span>
            <span className="font-mono text-xs">
              {new Date().toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}






