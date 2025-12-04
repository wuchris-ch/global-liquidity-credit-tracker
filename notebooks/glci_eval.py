#!/usr/bin/env python3
"""
GLCI Evaluation Script

This script runs backtests and generates visualizations for the
Global Liquidity & Credit Index (GLCI).

Usage:
    python notebooks/glci_eval.py
    python notebooks/glci_eval.py --start 2015-01-01 --save-plots
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np

# Check for matplotlib
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not available. Install with: pip install matplotlib")

from src.indicators import GLCIComputer, Aggregator, compute_glci
from src.etl import DataFetcher, DataStorage


def compute_and_evaluate(
    start_date: str | None = None,
    end_date: str | None = None,
    save_plots: bool = False
) -> dict:
    """Compute GLCI and run evaluation.
    
    Returns:
        Dict with evaluation results
    """
    print("=" * 60)
    print("GLCI EVALUATION")
    print("=" * 60)
    
    # 1. Compute GLCI
    print("\n1. Computing GLCI...")
    computer = GLCIComputer()
    
    try:
        result = computer.compute(start_date, end_date, save_output=True)
    except Exception as e:
        print(f"Error computing GLCI: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
    
    glci_df = result.glci
    pillars_df = result.pillars
    regimes_df = result.regimes
    
    print(f"   Date range: {glci_df['date'].min()} to {glci_df['date'].max()}")
    print(f"   Observations: {len(glci_df)}")
    
    # 2. Basic Statistics
    print("\n2. GLCI Statistics:")
    print(f"   Mean: {glci_df['value'].mean():.2f}")
    print(f"   Std:  {glci_df['value'].std():.2f}")
    print(f"   Min:  {glci_df['value'].min():.2f}")
    print(f"   Max:  {glci_df['value'].max():.2f}")
    print(f"   Latest: {glci_df['value'].iloc[-1]:.2f}")
    
    # 3. Regime Analysis
    print("\n3. Regime Analysis:")
    regime_stats = regimes_df["regime_label"].value_counts()
    for regime, count in regime_stats.items():
        pct = count / len(regimes_df) * 100
        print(f"   {regime:>8}: {count:>4} periods ({pct:>5.1f}%)")
    
    # Current regime
    current_regime = regimes_df.iloc[-1]["regime_label"]
    current_zscore = regimes_df.iloc[-1]["zscore"]
    print(f"\n   Current regime: {current_regime} (z-score: {current_zscore:.2f})")
    
    # 4. Pillar Contributions
    print("\n4. Pillar Contributions (latest):")
    pillar_weights = result.weights["pillar_weights"]
    latest_pillars = pillars_df.iloc[-1]
    
    for pillar in ["liquidity", "credit", "stress"]:
        if pillar in pillars_df.columns:
            value = latest_pillars[pillar]
            weight = pillar_weights.get(pillar, 0)
            contribution = value * weight
            print(f"   {pillar:>12}: value={value:>7.2f}, weight={weight:.0%}, contrib={contribution:>7.2f}")
    
    # 5. Correlation with existing indices
    print("\n5. Correlation with Other Indices:")
    aggregator = Aggregator()
    
    try:
        fed_liq = aggregator.compute_index("fed_net_liquidity", start_date, end_date)
        if not fed_liq.empty:
            # Align dates
            merged = pd.merge(
                glci_df[["date", "value"]].rename(columns={"value": "glci"}),
                fed_liq[["date", "value"]].rename(columns={"value": "fed_liq"}),
                on="date",
                how="inner"
            )
            if len(merged) > 10:
                corr = merged["glci"].corr(merged["fed_liq"])
                print(f"   GLCI vs Fed Net Liquidity: {corr:.3f}")
    except Exception as e:
        print(f"   Could not compute Fed Net Liquidity correlation: {e}")
    
    try:
        stress = aggregator.compute_index("usd_funding_stress", start_date, end_date)
        if not stress.empty:
            merged = pd.merge(
                glci_df[["date", "value"]].rename(columns={"value": "glci"}),
                stress[["date", "value"]].rename(columns={"value": "stress"}),
                on="date",
                how="inner"
            )
            if len(merged) > 10:
                corr = merged["glci"].corr(merged["stress"])
                print(f"   GLCI vs USD Funding Stress: {corr:.3f}")
    except Exception as e:
        print(f"   Could not compute Funding Stress correlation: {e}")
    
    # 6. Stress Episode Analysis
    print("\n6. Stress Episode Analysis:")
    stress_episodes = [
        ("2008 Financial Crisis", "2008-09-01", "2009-03-31"),
        ("COVID-19 Crash", "2020-02-15", "2020-04-15"),
        ("2022 QT/Rate Hikes", "2022-01-01", "2022-12-31"),
    ]
    
    for name, ep_start, ep_end in stress_episodes:
        mask = (glci_df["date"] >= ep_start) & (glci_df["date"] <= ep_end)
        episode_data = glci_df[mask]
        
        if len(episode_data) > 0:
            min_val = episode_data["value"].min()
            max_val = episode_data["value"].max()
            mean_val = episode_data["value"].mean()
            print(f"   {name}:")
            print(f"     Min: {min_val:.1f}, Max: {max_val:.1f}, Mean: {mean_val:.1f}")
        else:
            print(f"   {name}: No data available")
    
    # 7. Generate Plots
    if HAS_MATPLOTLIB and save_plots:
        print("\n7. Generating Plots...")
        plot_dir = project_root / "data" / "curated" / "plots"
        plot_dir.mkdir(parents=True, exist_ok=True)
        
        generate_plots(glci_df, pillars_df, regimes_df, result.weights, plot_dir)
        print(f"   Plots saved to {plot_dir}")
    
    # 8. Summary
    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)
    
    return {
        "glci": glci_df,
        "pillars": pillars_df,
        "regimes": regimes_df,
        "weights": result.weights,
        "metadata": result.metadata
    }


def generate_plots(
    glci_df: pd.DataFrame,
    pillars_df: pd.DataFrame,
    regimes_df: pd.DataFrame,
    weights: dict,
    output_dir: Path
):
    """Generate evaluation plots."""
    if not HAS_MATPLOTLIB:
        return
    
    # Set style
    plt.style.use("seaborn-v0_8-whitegrid")
    
    # 1. GLCI Time Series with Regimes
    fig, ax = plt.subplots(figsize=(14, 6))
    
    dates = pd.to_datetime(glci_df["date"])
    values = glci_df["value"]
    
    ax.plot(dates, values, "b-", linewidth=1.5, label="GLCI")
    ax.axhline(y=100, color="gray", linestyle="--", alpha=0.5)
    
    # Shade regimes
    regimes = regimes_df["regime"].values
    for i in range(len(dates) - 1):
        if regimes[i] == 1:  # Loose
            ax.axvspan(dates.iloc[i], dates.iloc[i+1], alpha=0.2, color="green")
        elif regimes[i] == -1:  # Tight
            ax.axvspan(dates.iloc[i], dates.iloc[i+1], alpha=0.2, color="red")
    
    ax.set_title("Global Liquidity & Credit Index (GLCI)", fontsize=14)
    ax.set_xlabel("Date")
    ax.set_ylabel("Index Value")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    
    plt.tight_layout()
    plt.savefig(output_dir / "glci_timeseries.png", dpi=150)
    plt.close()
    
    # 2. Pillar Contributions
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    
    dates = pd.to_datetime(pillars_df["date"])
    pillar_names = ["liquidity", "credit", "stress"]
    colors = ["blue", "green", "red"]
    
    for ax, pillar, color in zip(axes, pillar_names, colors):
        if pillar in pillars_df.columns:
            ax.plot(dates, pillars_df[pillar], color=color, linewidth=1.5)
            ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
            weight = weights["pillar_weights"].get(pillar, 0)
            ax.set_title(f"{pillar.title()} Factor (weight: {weight:.0%})")
            ax.set_ylabel("Factor Value")
    
    axes[-1].set_xlabel("Date")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    
    plt.tight_layout()
    plt.savefig(output_dir / "glci_pillars.png", dpi=150)
    plt.close()
    
    # 3. Regime Distribution
    fig, ax = plt.subplots(figsize=(8, 6))
    
    regime_counts = regimes_df["regime_label"].value_counts()
    colors_map = {"tight": "red", "neutral": "gray", "loose": "green"}
    colors = [colors_map.get(r, "blue") for r in regime_counts.index]
    
    ax.bar(regime_counts.index, regime_counts.values, color=colors, alpha=0.7)
    ax.set_title("Regime Distribution")
    ax.set_xlabel("Regime")
    ax.set_ylabel("Number of Periods")
    
    for i, (regime, count) in enumerate(regime_counts.items()):
        pct = count / len(regimes_df) * 100
        ax.text(i, count + 5, f"{pct:.1f}%", ha="center")
    
    plt.tight_layout()
    plt.savefig(output_dir / "glci_regimes.png", dpi=150)
    plt.close()
    
    print("   Generated: glci_timeseries.png, glci_pillars.png, glci_regimes.png")


def main():
    parser = argparse.ArgumentParser(description="GLCI Evaluation Script")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    parser.add_argument("--save-plots", action="store_true", help="Save plots to disk")
    
    args = parser.parse_args()
    
    start = args.start or (datetime.now() - timedelta(days=365*5)).strftime("%Y-%m-%d")
    end = args.end or datetime.now().strftime("%Y-%m-%d")
    
    compute_and_evaluate(start, end, save_plots=args.save_plots)


if __name__ == "__main__":
    main()



