import { InfoTooltipProps } from "@/components/info-tooltip";

/**
 * Centralized technical definitions for all indicators, metrics, and charts.
 * These provide detailed explanations for the info tooltips throughout the app.
 */

// =============================================================================
// METRIC CARDS - Dashboard & Page Level Indicators
// =============================================================================

export const metricDefinitions: Record<string, InfoTooltipProps> = {
  // Federal Reserve
  fed_balance_sheet: {
    title: "Federal Reserve Balance Sheet",
    description: "Total assets held by the Federal Reserve System",
    calculation: "Sum of all Fed holdings: Treasuries, MBS, loans, and other assets",
    source: "Federal Reserve H.4.1 Release (FRED: WALCL)",
    frequency: "Weekly (Wednesday close)",
    interpretation: "Expansion indicates QE/liquidity injection; contraction (QT) reduces system liquidity. Key driver of risk asset performance.",
  },

  sofr_rate: {
    title: "SOFR (Secured Overnight Financing Rate)",
    description: "Benchmark rate for overnight Treasury repo transactions",
    calculation: "Volume-weighted median of overnight Treasury repo transactions",
    source: "NY Federal Reserve (FRED: SOFR)",
    frequency: "Daily",
    interpretation: "Reflects cost of secured overnight funding. Elevated levels relative to Fed Funds suggest funding pressure.",
  },

  hy_spread: {
    title: "High Yield OAS",
    description: "ICE BofA US High Yield Index option-adjusted spread",
    calculation: "Yield spread of HY bonds over comparable Treasury yield curve, adjusted for embedded options",
    source: "ICE Data Indices via FRED (BAMLH0A0HYM2)",
    frequency: "Daily",
    interpretation: "Measures credit risk premium for below-investment-grade debt. Widening signals risk-off; tightening signals risk-on.",
  },

  net_liquidity: {
    title: "Fed Net Liquidity",
    description: "Effective liquidity available to financial markets",
    calculation: "Fed Total Assets − TGA − Reverse Repo Facility",
    source: "Calculated from FRED series: WALCL, WTREGEN, RRPONTSYD",
    frequency: "Weekly (aligned to Wednesday)",
    sections: [
      { label: "TGA Effect", content: "Treasury spending from TGA injects liquidity; debt issuance drains it" },
      { label: "RRP Effect", content: "Money parked in RRP is removed from active circulation" },
    ],
    interpretation: "Rising net liquidity historically correlates with equity market strength. Falls below ~$5.5T have preceded market stress.",
  },

  // Treasury General Account
  tga: {
    title: "Treasury General Account",
    description: "US Treasury's operating cash balance at the Federal Reserve",
    calculation: "Direct observation of Treasury's Fed account balance",
    source: "Federal Reserve H.4.1 Release (FRED: WTREGEN)",
    frequency: "Weekly",
    interpretation: "Large TGA balances drain liquidity; Treasury spending releases liquidity back into the system.",
  },

  // Reverse Repo
  rrp: {
    title: "Overnight Reverse Repo Facility",
    description: "Fed facility where counterparties lend cash overnight against Treasuries",
    calculation: "Total value of overnight RRP transactions accepted by NY Fed",
    source: "NY Federal Reserve (FRED: RRPONTSYD)",
    frequency: "Daily",
    interpretation: "High RRP usage indicates excess cash in money markets. Declining RRP releases liquidity as cash seeks higher-yielding assets.",
  },

  // Central Banks
  ecb_assets: {
    title: "ECB Balance Sheet",
    description: "Total assets of the European Central Bank",
    calculation: "Consolidated balance sheet of ECB and national central banks",
    source: "ECB Statistical Data Warehouse via FRED (ECBASSETSW)",
    frequency: "Weekly",
    interpretation: "Euro area monetary policy stance. APP/PEPP purchases expand; redemptions contract.",
  },

  boj_assets: {
    title: "Bank of Japan Balance Sheet",
    description: "Total assets held by the Bank of Japan",
    calculation: "Sum of BoJ holdings including JGBs, ETFs, and other securities",
    source: "Bank of Japan via FRED (JPNASSETS)",
    frequency: "Monthly",
    interpretation: "BoJ maintains significant holdings via YCC policy. Changes signal policy shifts.",
  },

  // Credit Spreads
  ig_spread: {
    title: "Investment Grade OAS",
    description: "ICE BofA US Corporate Index option-adjusted spread",
    calculation: "Yield spread of IG corporate bonds over Treasuries, option-adjusted",
    source: "ICE Data Indices via FRED (BAMLC0A0CM)",
    frequency: "Daily",
    interpretation: "Measures credit risk premium for investment-grade debt. More stable than HY; widening signals broader risk concerns.",
  },

  effr: {
    title: "Effective Federal Funds Rate",
    description: "Weighted average rate on overnight unsecured Fed Funds transactions",
    calculation: "Volume-weighted median of brokered Fed Funds trades",
    source: "NY Federal Reserve (FRED: DFF)",
    frequency: "Daily",
    interpretation: "Primary policy rate target. Should trade within Fed's target range.",
  },
};

// =============================================================================
// CHART DEFINITIONS
// =============================================================================

export const chartDefinitions: Record<string, InfoTooltipProps> = {
  // Main Charts
  fed_balance_sheet_chart: {
    title: "Federal Reserve Balance Sheet",
    description: "Total assets held by the Federal Reserve over time",
    source: "FRED: WALCL (weekly H.4.1 release)",
    interpretation: "Track QE/QT cycles. Expansion correlates with risk-on; contraction with tighter conditions.",
  },

  net_liquidity_chart: {
    title: "Fed Net Liquidity",
    description: "Total Assets minus TGA and Reverse Repo",
    calculation: "WALCL − WTREGEN − (RRPONTSYD × 1000)",
    source: "Calculated composite from Federal Reserve data",
    interpretation: "Most accurate measure of 'spendable' liquidity in the financial system.",
  },

  funding_rates_chart: {
    title: "Funding Rates Comparison",
    description: "Key overnight secured and unsecured rates",
    sections: [
      { label: "SOFR", content: "Secured rate based on Treasury repo (FRED: SOFR)" },
      { label: "EFFR", content: "Unsecured interbank rate (FRED: DFF)" },
    ],
    interpretation: "SOFR-EFFR spread indicates relative stress in secured vs unsecured markets.",
  },

  credit_spreads_chart: {
    title: "Credit Spreads",
    description: "Option-adjusted spreads for corporate bonds vs Treasuries",
    sections: [
      { label: "High Yield", content: "Below investment grade (BB+ and lower) corporate bonds" },
      { label: "IG", content: "Investment grade (BBB- and higher) corporate bonds" },
    ],
    source: "ICE BofA Indices via FRED",
    interpretation: "HY leads equities; widening often precedes market weakness. HY/IG ratio indicates risk appetite.",
  },

  central_banks_chart: {
    title: "Central Bank Balance Sheets",
    description: "Major central bank assets indexed to period start (100)",
    calculation: "Each CB's assets normalized: (current / start) × 100",
    sections: [
      { label: "Fed", content: "US Federal Reserve total assets" },
      { label: "ECB", content: "European Central Bank consolidated balance sheet" },
      { label: "BoJ", content: "Bank of Japan total assets" },
    ],
    interpretation: "Coordinated expansion supports global risk assets; divergence creates cross-asset opportunities.",
  },

  sofr_rate_chart: {
    title: "SOFR Rate History",
    description: "Secured Overnight Financing Rate over time",
    source: "NY Federal Reserve (FRED: SOFR)",
    interpretation: "Benchmark for $200T+ derivatives. Spikes indicate repo market stress (cf. Sept 2019).",
  },

  hy_spread_chart: {
    title: "High Yield Spread History",
    description: "ICE BofA US High Yield Index OAS",
    source: "ICE Data Indices (FRED: BAMLH0A0HYM2)",
    sections: [
      { label: "Tight", content: "< 300 bps historically indicates complacency" },
      { label: "Average", content: "~400-500 bps represents normal conditions" },
      { label: "Stress", content: "> 600 bps signals credit market distress" },
    ],
    interpretation: "Leading indicator for equity corrections. Watch for rapid widening.",
  },

  stress_index_chart: {
    title: "Funding Stress Index",
    description: "Z-score composite measuring funding market conditions",
    calculation: "Weighted average of z-scored: TED spread, HY OAS, IG OAS",
    source: "Calculated from FRED data",
    sections: [
      { label: "< -0.5", content: "Low stress - ample funding liquidity" },
      { label: "-0.5 to 0.5", content: "Normal conditions" },
      { label: "> 1.0", content: "Elevated stress - risk-off positioning warranted" },
    ],
    interpretation: "Real-time gauge of funding market health. Extreme readings are mean-reverting.",
  },
};

// =============================================================================
// GLCI-SPECIFIC DEFINITIONS
// =============================================================================

export const glciDefinitions: Record<string, InfoTooltipProps> = {
  glci_index: {
    title: "Global Liquidity & Credit Index (GLCI)",
    description: "Tri-pillar composite measuring global financial conditions",
    calculation: "PCA-extracted latent factors from each pillar, weighted and normalized to mean=100, stdev=10",
    sections: [
      { label: "Liquidity", content: "40% weight — CB balance sheets, M2, reserves" },
      { label: "Credit", content: "35% weight — bank credit, consumer credit, BIS data" },
      { label: "Stress", content: "25% weight — spreads, funding rates, VIX (inverted)" },
    ],
    interpretation: "Above 110 = loose conditions (risk-on); below 90 = tight (risk-off). Strong correlation with equity returns.",
  },

  glci_zscore: {
    title: "GLCI Z-Score",
    description: "Standardized deviation from historical mean",
    calculation: "(Current GLCI − Long-term Mean) / Standard Deviation",
    interpretation: "Z > 1: Loose regime. Z < -1: Tight regime. Values > |2| are historically rare.",
  },

  glci_momentum: {
    title: "GLCI Momentum",
    description: "Rate of change in the index value",
    calculation: "4-week exponential moving average of weekly changes",
    interpretation: "Positive momentum in loose regime = continue bullish. Negative momentum in tight regime = increase caution.",
  },

  pillar_liquidity: {
    title: "Liquidity Pillar",
    description: "Measures global monetary base and central bank policy stance",
    calculation: "First principal component of standardized and growth-transformed series",
    sections: [
      { label: "Components", content: "Fed assets, ECB assets, BoJ assets, reserve balances, M2, minus TGA and RRP" },
      { label: "Weight", content: "40% of total GLCI" },
    ],
    interpretation: "Positive values indicate expansionary monetary conditions globally.",
  },

  pillar_credit: {
    title: "Credit Pillar",
    description: "Measures private sector credit growth and availability",
    calculation: "First principal component of credit-related series",
    sections: [
      { label: "Components", content: "Bank credit, loans & leases, consumer credit, commercial paper, BIS credit data" },
      { label: "Weight", content: "35% of total GLCI" },
    ],
    interpretation: "Positive values indicate healthy credit expansion; negative suggests deleveraging.",
  },

  pillar_stress: {
    title: "Funding Stress Pillar",
    description: "Measures financial market stress (inverted in GLCI)",
    calculation: "First principal component of stress indicators, sign-flipped",
    sections: [
      { label: "Components", content: "HY spread, IG spread, TED spread, SOFR, Fed Funds, VIX, NFCI" },
      { label: "Weight", content: "25% of total GLCI" },
      { label: "Note", content: "Higher stress = lower contribution to GLCI" },
    ],
    interpretation: "Negative values indicate elevated stress; positive indicates calm markets.",
  },

  regime_classification: {
    title: "Regime Classification",
    description: "Current liquidity regime based on GLCI z-score",
    calculation: "Tight: z < -1 | Neutral: -1 ≤ z ≤ 1 | Loose: z > 1",
    interpretation: "Regimes tend to persist; transitions are meaningful signals for asset allocation.",
  },

  regime_change_prob: {
    title: "Regime Change Probability",
    description: "Estimated probability of transitioning to a different regime",
    calculation: "Based on distance to regime boundaries and current momentum",
    sections: [
      { label: "Low (< 25%)", content: "Current regime likely to persist" },
      { label: "Medium (25-50%)", content: "Monitor closely for transition signals" },
      { label: "High (> 50%)", content: "Regime change likely imminent" },
    ],
    interpretation: "Use for tactical positioning ahead of regime shifts.",
  },

  waterfall_breakdown: {
    title: "Weekly Change Breakdown",
    description: "Contribution of each pillar to the weekly GLCI change",
    calculation: "Pillar contribution = Pillar change × Pillar weight",
    interpretation: "Identify which pillar is driving the overall index movement.",
  },
};

// =============================================================================
// SPREAD ANALYSIS DEFINITIONS
// =============================================================================

export const spreadDefinitions: Record<string, InfoTooltipProps> = {
  spread_decomposition: {
    title: "Spread Decomposition",
    description: "Estimated components of the high yield credit spread",
    calculation: "Academic research-based decomposition (approximate)",
    sections: [
      { label: "Default Risk", content: "~45% — Expected loss from defaults" },
      { label: "Liquidity", content: "~25% — Illiquidity premium for corporate bonds" },
      { label: "Risk Aversion", content: "~18% — Systematic risk premium" },
      { label: "Other", content: "~12% — Tax, regulatory, and structural factors" },
    ],
    source: "Based on methodology from Gilchrist & Zakrajšek (2012)",
    interpretation: "Understanding composition helps identify why spreads are moving.",
  },

  hy_ig_ratio: {
    title: "HY/IG Spread Ratio",
    description: "Relative pricing of high yield vs investment grade credit",
    calculation: "HY OAS ÷ IG OAS",
    interpretation: "Higher ratio indicates more discrimination between credit qualities; compression suggests risk-seeking behavior.",
  },

  recession_comparison: {
    title: "Recession Average",
    description: "Historical average HY spread during recession periods",
    source: "NBER recession dates applied to historical spread data",
    interpretation: "Current spread as % of recession average indicates relative stress level.",
  },
};

// =============================================================================
// EXPLORER & DATA DEFINITIONS
// =============================================================================

export const explorerDefinitions: Record<string, InfoTooltipProps> = {
  normalized_view: {
    title: "Normalized View",
    description: "All series indexed to 100 at start of selected period",
    calculation: "(Current value / First value) × 100",
    interpretation: "Compare relative performance across series with different units and scales.",
  },

  absolute_view: {
    title: "Absolute Values",
    description: "Raw values in original units",
    interpretation: "See actual levels; be aware different series have different scales.",
  },

  series_comparison: {
    title: "Series Comparison",
    description: "Multi-series chart for analyzing relationships",
    interpretation: "Look for correlations, divergences, and lead-lag relationships between series.",
  },
};

// =============================================================================
// DATA FRESHNESS DEFINITIONS
// =============================================================================

export const dataFreshnessDefinitions: Record<string, InfoTooltipProps> = {
  freshness_status: {
    title: "Data Freshness",
    description: "How recently each data source was updated",
    sections: [
      { label: "Fresh", content: "< 7 days old — Normal for most series" },
      { label: "Stale", content: "7-30 days — May need manual refresh" },
      { label: "Old", content: "> 30 days — Data source may have issues" },
    ],
    interpretation: "Most series update daily/weekly. Quarterly series (BIS) naturally lag.",
  },
};

// =============================================================================
// REGIME TIMELINE DEFINITIONS  
// =============================================================================

export const regimeDefinitions: Record<string, InfoTooltipProps> = {
  regime_history: {
    title: "Regime History",
    description: "Historical classification of liquidity regimes over time",
    calculation: "Weekly GLCI z-score mapped to regimes: Tight (z<-1), Neutral (-1≤z≤1), Loose (z>1)",
    interpretation: "Shows duration and frequency of each regime. Long neutral periods are typical.",
  },

  regime_distribution: {
    title: "Regime Distribution",
    description: "Time spent in each regime during selected period",
    calculation: "Weeks in regime ÷ Total weeks × 100",
    interpretation: "Compare to long-term averages: ~25% loose, ~50% neutral, ~25% tight.",
  },
};

// =============================================================================
// PREDICTIVE PANEL DEFINITIONS
// =============================================================================

export const predictiveDefinitions: Record<string, InfoTooltipProps> = {
  momentum_indicator: {
    title: "Momentum",
    description: "Weekly rate of change in GLCI",
    calculation: "4-week exponential moving average of weekly changes",
    interpretation: "Positive = improving conditions; Negative = deteriorating. Consider alongside regime.",
  },

  projection_4w: {
    title: "4-Week Projection",
    description: "Simple linear extrapolation based on current momentum",
    calculation: "Current Value + (Momentum × 4)",
    interpretation: "Illustrative only — not a forecast. Actual path depends on incoming data.",
  },

  volatility_assessment: {
    title: "Volatility Assessment",
    description: "Near-term regime stability indicator",
    calculation: "Based on regime change probability",
    sections: [
      { label: "Low", content: "Stable regime, probability of change < 25%" },
      { label: "Medium", content: "Some uncertainty, probability 25-50%" },
      { label: "High", content: "Elevated transition risk, probability > 50%" },
    ],
    interpretation: "High volatility periods warrant closer monitoring and defensive positioning.",
  },
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/** Get metric definition by key, with fallback */
export function getMetricInfo(key: string): InfoTooltipProps | undefined {
  return metricDefinitions[key];
}

/** Get chart definition by key, with fallback */
export function getChartInfo(key: string): InfoTooltipProps | undefined {
  return chartDefinitions[key];
}

/** Get GLCI-specific definition */
export function getGLCIInfo(key: string): InfoTooltipProps | undefined {
  return glciDefinitions[key];
}

/** Get spread analysis definition */
export function getSpreadInfo(key: string): InfoTooltipProps | undefined {
  return spreadDefinitions[key];
}

/** Get any definition by key, searching all categories */
export function getInfoDefinition(key: string): InfoTooltipProps | undefined {
  return (
    metricDefinitions[key] ||
    chartDefinitions[key] ||
    glciDefinitions[key] ||
    spreadDefinitions[key] ||
    explorerDefinitions[key] ||
    dataFreshnessDefinitions[key] ||
    regimeDefinitions[key] ||
    predictiveDefinitions[key]
  );
}



