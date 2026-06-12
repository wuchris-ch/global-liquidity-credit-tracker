"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { href: "/", label: "Today" },
  { href: "/glci", label: "Index" },
  { href: "/flows", label: "Flows" },
  { href: "/playbook", label: "Playbook" },
  { href: "/plumbing", label: "Plumbing" },
  { href: "/explorer", label: "Explorer" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Masthead() {
  const pathname = usePathname();
  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return (
    <header className="border-b border-border bg-background">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-8">
        <div className="flex items-baseline justify-between gap-4 pt-5 pb-3 sm:pt-7">
          <Link href="/" className="min-w-0">
            <span className="font-serif text-xl font-medium tracking-tight sm:text-2xl">
              Global Liquidity <span className="text-muted-foreground">&amp;</span> Credit
            </span>
          </Link>
          <time
            dateTime={new Date().toISOString().slice(0, 10)}
            className="hidden shrink-0 font-mono text-xs text-muted-foreground sm:block"
          >
            {today}
          </time>
        </div>
        <nav aria-label="Sections" className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <ul className="flex gap-6">
            {SECTIONS.map(({ href, label }) => {
              const active = isActive(pathname, href);
              return (
                <li key={href} className="shrink-0">
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "block border-b-2 pb-2.5 text-[0.8125rem] font-medium tracking-wide transition-colors",
                      active
                        ? "border-foreground text-foreground"
                        : "border-transparent text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </header>
  );
}
