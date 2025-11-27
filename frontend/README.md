# Global Liquidity Tracker - Frontend

A beautiful, modern dashboard for tracking global liquidity and credit metrics built with Next.js 16, shadcn/ui, and Recharts.

## Features

- **Dashboard** - Real-time overview of key liquidity metrics with interactive charts
- **Liquidity Monitor** - Deep dive into Fed balance sheet and net liquidity calculations
- **Credit Spreads** - Credit market stress indicators and spread analysis
- **Data Explorer** - Compare and analyze multiple data series

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **UI Components**: shadcn/ui
- **Charts**: Recharts
- **Styling**: Tailwind CSS v4
- **State Management**: TanStack Query
- **Typography**: Sora + IBM Plex Mono

## Getting Started

1. Install dependencies:
   ```bash
   npm install
   ```

2. Run the development server:
   ```bash
   npm run dev
   ```

3. Open [http://localhost:3000](http://localhost:3000)

## Connecting to Python Backend

The frontend fetches live data from the Python API server. Start the backend first:

```bash
# From the project root
uvicorn src.api:app --reload --port 8000
```

Then run the frontend:

```bash
npm run dev
```

The frontend will automatically connect to `http://localhost:8000`. To use a different URL, set `NEXT_PUBLIC_API_URL`:

```bash
NEXT_PUBLIC_API_URL=http://your-api-server:8000 npm run dev
```

## Design System

### Colors

The dashboard uses a sophisticated dark theme with cyan/teal accents:

- **Background**: Deep space dark (`oklch(0.08 0.01 260)`)
- **Primary**: Cyan accent (`oklch(0.75 0.18 200)`)
- **Positive**: Green indicators (`oklch(0.72 0.20 155)`)
- **Negative**: Red indicators (`oklch(0.65 0.25 25)`)

### Typography

- **Headings & Body**: Sora - A geometric sans-serif with excellent legibility
- **Numbers & Code**: IBM Plex Mono - Clean monospace for financial data

## Project Structure

```
src/
├── app/
│   ├── api/           # API routes for backend integration
│   ├── explorer/      # Data explorer page
│   ├── liquidity/     # Liquidity monitor page
│   ├── spreads/       # Credit spreads page
│   ├── layout.tsx     # Root layout with sidebar
│   └── page.tsx       # Dashboard page
├── components/
│   ├── ui/            # shadcn/ui components
│   ├── app-sidebar.tsx
│   ├── header.tsx
│   ├── liquidity-chart.tsx
│   ├── metric-card.tsx
│   └── multi-line-chart.tsx
├── hooks/
│   ├── use-mobile.ts
│   └── use-series-data.ts  # Data fetching hooks
└── lib/
    ├── api.ts         # API client for Python backend
    └── utils.ts
```

## License

MIT
