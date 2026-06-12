# Design

## Theme

Light-only. The surface is warm paper, the content is ink. No dark mode. Scene: a macro investor reading the morning brief over coffee at 7am in a bright room before the US open.

## Color

OKLCH throughout. Color strategy: Restrained. Regime color is the only committed color and appears only where it encodes regime (regime stamp, regime bands, regime-keyed table cells). Everything else is ink on paper.

- `--background` paper: `oklch(0.967 0.007 80)`
- `--card` raised paper: `oklch(0.982 0.005 80)`
- `--foreground` ink: `oklch(0.24 0.012 60)`
- `--muted-foreground` ink muted: `oklch(0.46 0.012 60)`
- `--border` hairline rule: `oklch(0.885 0.008 75)`
- `--primary` / links / selection, deep ink blue: `oklch(0.38 0.08 255)`
- Regime: loose `oklch(0.52 0.12 155)`, neutral `oklch(0.55 0.09 75)`, tight `oklch(0.50 0.17 27)` (text-grade, AA on paper; always paired with a text label)
- Pillars: liquidity `oklch(0.48 0.09 245)`, credit `oklch(0.55 0.08 75)`, stress `oklch(0.50 0.13 30)`
- Charts: ink shades first (`oklch(0.30 0.01 60)`, `0.50`, `0.65`), accent blue second; series color never decorative.

## Typography

- Display / headlines / verdicts / prose: **Newsreader** (serif, next/font/google), tight leading on display sizes, opsz auto.
- UI labels, nav, controls, table headers: **Geist Sans**.
- All figures and data: **Geist Mono**, `font-variant-numeric: tabular-nums`.
- Scale: display 2.5–3rem, h2 1.5rem, body 1rem/1.6, data captions 0.8125rem. Body prose measure 65–72ch.

## Layout

- Masthead top navigation (publication-style): wordmark left, five sections (Today, Index, Playbook, Plumbing, Explorer), dateline + data freshness right. Hairline rule below. No sidebar.
- Content column: max-w ~72rem, generous top whitespace; prose blocks capped near 70ch.
- Hairline horizontal rules separate sections, not cards. Cards only for genuinely card-shaped things (vitals tiles); never nested.
- Charts sit directly on paper (no card chrome): title, one-line reading, chart, source line.

## Components

- Regime stamp: small uppercase mono label with regime-tinted background (`color-mix` 12% on paper) and regime-color text, e.g. "LOOSE · 14TH WEEK".
- Vitals strip: row of compact tiles, mono figures, tiny sparkline, change vs prior period.
- Tables: hairline rules, no zebra, right-aligned mono figures, regime columns tinted at 8%.
- Tooltips: paper background, hairline border, small shadow.
- Skeletons: paper-toned shimmer blocks matching final layout.

## Motion

Minimal. 150–200ms ease-out state transitions only. No page-load choreography, no decorative motion. Respect `prefers-reduced-motion`.

## Banned here

Dark-terminal pastiche, gradient text, glassmorphism, glow effects, side-stripe accents, identical metric-card grids, hero-metric template.
