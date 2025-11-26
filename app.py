"""Streamlit dashboard for Global Liquidity Tracker."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os

# Set page config first
st.set_page_config(
    page_title="Global Liquidity Tracker",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for sophisticated black/white aesthetic
st.markdown("""
<style>
    /* Import distinctive fonts */
    @import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    /* Root variables */
    :root {
        --bg-primary: #0a0a0a;
        --bg-secondary: #111111;
        --bg-card: #161616;
        --bg-card-hover: #1a1a1a;
        --border-color: #262626;
        --text-primary: #fafafa;
        --text-secondary: #a1a1a1;
        --text-muted: #525252;
        --accent: #ffffff;
        --accent-dim: #737373;
        --positive: #22c55e;
        --negative: #ef4444;
    }
    
    /* Main app styling */
    .stApp {
        background-color: var(--bg-primary);
        font-family: 'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Main content area */
    .main .block-container {
        padding: 2rem 3rem;
        max-width: 1600px;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: var(--bg-secondary);
        border-right: 1px solid var(--border-color);
    }
    
    [data-testid="stSidebar"] .stMarkdown {
        color: var(--text-secondary);
    }
    
    /* Typography */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Instrument Sans', sans-serif !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
    }
    
    h1 {
        font-size: 2.5rem !important;
        font-weight: 700 !important;
        margin-bottom: 0.5rem !important;
    }
    
    h2 {
        font-size: 1.5rem !important;
        margin-top: 2rem !important;
    }
    
    h3 {
        font-size: 1.125rem !important;
        color: var(--text-secondary) !important;
        font-weight: 500 !important;
    }
    
    p, span, div {
        color: var(--text-secondary);
    }
    
    /* Metric cards */
    [data-testid="stMetric"] {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1.25rem 1rem;
        transition: all 0.2s ease;
    }
    
    [data-testid="stMetric"]:hover {
        background: var(--bg-card-hover);
        border-color: #404040;
    }
    
    [data-testid="stMetric"] label {
        color: var(--text-muted) !important;
        font-size: 0.65rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.04em !important;
        font-weight: 500 !important;
    }
    
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: var(--text-primary) !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 1.35rem !important;
        font-weight: 500 !important;
    }
    
    [data-testid="stMetric"] [data-testid="stMetricDelta"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.75rem !important;
    }
    
    [data-testid="stMetric"] > div > div {
        gap: 0.25rem !important;
    }
    
    /* Selectbox and inputs */
    [data-testid="stSelectbox"] label,
    [data-testid="stMultiSelect"] label,
    [data-testid="stDateInput"] label,
    [data-testid="stCheckbox"] label {
        color: var(--text-secondary) !important;
        font-size: 0.75rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        font-weight: 500 !important;
    }
    
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stMultiSelect"] > div > div {
        background-color: var(--bg-card) !important;
        border-color: var(--border-color) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
    }
    
    /* Date input */
    [data-testid="stDateInput"] input {
        background-color: var(--bg-card) !important;
        border-color: var(--border-color) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
        font-family: 'JetBrains Mono', monospace !important;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: var(--text-primary) !important;
        color: var(--bg-primary) !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        padding: 0.5rem 1.25rem !important;
        transition: all 0.2s ease !important;
    }
    
    .stButton > button:hover {
        background-color: var(--text-secondary) !important;
        transform: translateY(-1px);
    }
    
    /* Spinner */
    [data-testid="stSpinner"] {
        color: var(--text-primary) !important;
    }
    
    /* Expander */
    [data-testid="stExpander"] {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
    }
    
    [data-testid="stExpander"] summary {
        color: var(--text-primary) !important;
    }
    
    /* Dataframe */
    [data-testid="stDataFrame"] {
        background-color: var(--bg-card) !important;
        border-radius: 12px !important;
    }
    
    /* Warning and error messages */
    .stAlert {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
        color: var(--text-secondary) !important;
    }
    
    /* Plotly chart container */
    [data-testid="stPlotlyChart"] {
        background-color: transparent;
        border-radius: 12px;
    }
    
    /* Checkbox */
    [data-testid="stCheckbox"] span {
        color: var(--text-secondary) !important;
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--bg-secondary);
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--border-color);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #404040;
    }
    
    /* Custom header component */
    .custom-header {
        display: flex;
        align-items: center;
        gap: 1.25rem;
        margin-bottom: 2.5rem;
        padding-bottom: 2rem;
        border-bottom: 1px solid var(--border-color);
    }
    
    .custom-header .logo {
        width: 48px;
        height: 48px;
        background: linear-gradient(135deg, #fafafa 0%, #d4d4d4 100%);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        color: var(--bg-primary);
        font-size: 1.5rem;
        flex-shrink: 0;
    }
    
    .custom-header .title-group h1 {
        margin: 0 !important;
        line-height: 1.1 !important;
        font-size: 2rem !important;
    }
    
    .custom-header .subtitle {
        color: var(--text-muted);
        font-size: 0.875rem;
        margin-top: 0.375rem;
        letter-spacing: 0.01em;
    }
    
    /* Sidebar improvements */
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 2rem;
    }
    
    /* Stats grid */
    .stat-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1.5rem;
        transition: all 0.2s ease;
    }
    
    .stat-card:hover {
        border-color: #404040;
    }
    
    .stat-label {
        color: var(--text-muted);
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 500;
        margin-bottom: 0.5rem;
    }
    
    .stat-value {
        color: var(--text-primary);
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.75rem;
        font-weight: 500;
    }
    
    .stat-delta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.875rem;
        margin-top: 0.25rem;
    }
    
    .stat-delta.positive {
        color: var(--positive);
    }
    
    .stat-delta.negative {
        color: var(--negative);
    }
    
    /* Section divider */
    .section-divider {
        height: 1px;
        background: var(--border-color);
        margin: 2rem 0;
    }
    
    /* View selector tabs look */
    .view-indicator {
        display: inline-block;
        padding: 0.5rem 1rem;
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 20px;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-secondary);
        margin-bottom: 1.5rem;
    }
    
    /* Sidebar header */
    .sidebar-header {
        font-size: 0.625rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-muted);
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid var(--border-color);
    }
    
    /* Card title */
    .card-title {
        font-size: 0.875rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    .card-title::before {
        content: '';
        width: 3px;
        height: 1rem;
        background: var(--text-primary);
        border-radius: 2px;
    }
    
    /* Custom metric cards */
    .metric-card {
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1.25rem 1rem;
        transition: all 0.2s ease;
        height: 100%;
        min-height: 120px;
    }
    
    .metric-card:hover {
        background: var(--bg-card-hover);
        border-color: #404040;
    }
    
    .metric-label {
        color: var(--text-muted);
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 500;
        margin-bottom: 0.625rem;
        line-height: 1.3;
    }
    
    .metric-value {
        color: var(--text-primary);
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.375rem;
        font-weight: 500;
        line-height: 1.1;
        white-space: nowrap;
    }
    
    .metric-delta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        margin-top: 0.5rem;
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }
    
    .metric-delta.positive {
        color: var(--positive);
    }
    
    .metric-delta.negative {
        color: var(--negative);
    }
    
    .metric-delta.positive::before {
        content: '↑';
    }
    
    .metric-delta.negative::before {
        content: '↓';
    }
</style>
""", unsafe_allow_html=True)

from src.config import FRED_API_KEY, get_all_series, get_all_indices
from src.etl import DataFetcher, DataStorage
from src.indicators import Aggregator, compute_zscore, resample_to_frequency


# Plotly theme configuration
CHART_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {
        "family": "Instrument Sans, -apple-system, BlinkMacSystemFont, sans-serif",
        "color": "#a1a1a1",
        "size": 12
    },
    "title": {
        "font": {
            "family": "Instrument Sans, -apple-system, BlinkMacSystemFont, sans-serif",
            "color": "#fafafa",
            "size": 16
        },
        "x": 0,
        "xanchor": "left"
    },
    "xaxis": {
        "gridcolor": "#262626",
        "linecolor": "#262626",
        "tickcolor": "#262626",
        "zerolinecolor": "#262626",
        "showgrid": True,
        "gridwidth": 1
    },
    "yaxis": {
        "gridcolor": "#262626",
        "linecolor": "#262626", 
        "tickcolor": "#262626",
        "zerolinecolor": "#262626",
        "showgrid": True,
        "gridwidth": 1
    },
    "legend": {
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"color": "#a1a1a1"}
    },
    "margin": {"t": 60, "b": 40, "l": 60, "r": 20},
    "hoverlabel": {
        "bgcolor": "#161616",
        "bordercolor": "#262626",
        "font": {"family": "JetBrains Mono, monospace", "color": "#fafafa", "size": 12}
    }
}

# Color palette for charts (monochrome with subtle variations)
CHART_COLORS = ["#ffffff", "#a1a1a1", "#737373", "#525252", "#404040"]


# Initialize components
@st.cache_resource
def get_fetcher():
    return DataFetcher()


@st.cache_resource
def get_storage():
    return DataStorage()


@st.cache_resource
def get_aggregator():
    return Aggregator(get_fetcher())


# Cache data fetching
@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_series_cached(series_id: str, start_date: str, end_date: str):
    fetcher = get_fetcher()
    return fetcher.fetch_series(series_id, start_date, end_date)


@st.cache_data(ttl=3600)
def compute_index_cached(index_id: str, start_date: str, end_date: str):
    aggregator = get_aggregator()
    return aggregator.compute_index(index_id, start_date, end_date)


def create_chart(df, x, y, title="", chart_type="line", color=None, show_title=True):
    """Create a styled Plotly chart."""
    if chart_type == "line":
        fig = px.line(df, x=x, y=y, color=color, color_discrete_sequence=CHART_COLORS)
    elif chart_type == "area":
        fig = px.area(df, x=x, y=y, color=color, color_discrete_sequence=CHART_COLORS)
    else:
        fig = px.line(df, x=x, y=y, color=color, color_discrete_sequence=CHART_COLORS)
    
    fig.update_layout(**CHART_LAYOUT)
    
    if show_title and title:
        fig.update_layout(title=title)
    else:
        fig.update_layout(title="")
    
    # Style the line
    fig.update_traces(
        line={"width": 2},
        hovertemplate="<b>%{x}</b><br>%{y:,.2f}<extra></extra>"
    )
    
    return fig


def main():
    # Custom header
    st.markdown("""
    <div class="custom-header">
        <div class="logo">◉</div>
        <div class="title-group">
            <h1>Global Liquidity Tracker</h1>
            <div class="subtitle">Central bank liquidity, credit conditions & funding stress</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Check API key
    if not FRED_API_KEY:
        st.error("⚠️ FRED API key not configured. Set FRED_API_KEY in your .env file.")
        st.info("Get a free API key at https://fred.stlouisfed.org/docs/api/api_key.html")
        st.stop()
    
    # Sidebar
    with st.sidebar:
        st.markdown('<div class="sidebar-header">Configuration</div>', unsafe_allow_html=True)
        
        # Date range
        default_start = datetime.now() - timedelta(days=365*3)
        start_date = st.date_input("Start Date", default_start)
        end_date = st.date_input("End Date", datetime.now())
        
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-header">Navigation</div>', unsafe_allow_html=True)
        
        # View selection
        view = st.selectbox(
            "View",
            ["Dashboard", "Individual Series", "Composite Indices", "Data Explorer"],
            label_visibility="collapsed"
        )
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-header">Data Sources</div>', unsafe_allow_html=True)
        
        st.markdown("""
        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
            <span style="font-size: 0.7rem; padding: 0.25rem 0.5rem; background: #1a1a1a; border-radius: 4px; color: #737373;">FRED</span>
            <span style="font-size: 0.7rem; padding: 0.25rem 0.5rem; background: #1a1a1a; border-radius: 4px; color: #737373;">NY Fed</span>
            <span style="font-size: 0.7rem; padding: 0.25rem 0.5rem; background: #1a1a1a; border-radius: 4px; color: #737373;">BIS</span>
            <span style="font-size: 0.7rem; padding: 0.25rem 0.5rem; background: #1a1a1a; border-radius: 4px; color: #737373;">World Bank</span>
        </div>
        """, unsafe_allow_html=True)
    
    # View indicator
    st.markdown(f'<div class="view-indicator">◉ {view}</div>', unsafe_allow_html=True)
    
    if view == "Dashboard":
        render_dashboard(start_str, end_str)
    elif view == "Individual Series":
        render_series_view(start_str, end_str)
    elif view == "Composite Indices":
        render_indices_view(start_str, end_str)
    elif view == "Data Explorer":
        render_explorer(start_str, end_str)


def render_dashboard(start_date: str, end_date: str):
    """Main dashboard view with key metrics."""
    
    # Key metrics row with better spacing
    col1, col2, col3, col4 = st.columns(4, gap="medium")
    
    # Fetch key series
    try:
        with st.spinner(""):
            fed_assets = fetch_series_cached("fed_total_assets", start_date, end_date)
            sofr = fetch_series_cached("sofr", start_date, end_date)
            hy_spread = fetch_series_cached("ice_bofa_us_high_yield_spread", start_date, end_date)
            us_m2 = fetch_series_cached("us_m2", start_date, end_date)
        
        # Display metrics using custom HTML for full control
        with col1:
            if not fed_assets.empty:
                latest = fed_assets.iloc[-1]["value"]
                prev = fed_assets.iloc[-2]["value"] if len(fed_assets) > 1 else latest
                delta = (latest - prev) / prev * 100
                delta_class = "positive" if delta >= 0 else "negative"
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Fed Balance Sheet</div>
                    <div class="metric-value">${latest/1e6:.2f}T</div>
                    <div class="metric-delta {delta_class}">{delta:+.2f}%</div>
                </div>
                """, unsafe_allow_html=True)
        
        with col2:
            if not sofr.empty:
                latest = sofr.iloc[-1]["value"]
                prev = sofr.iloc[-2]["value"] if len(sofr) > 1 else latest
                delta = latest - prev
                delta_class = "positive" if delta >= 0 else "negative"
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">SOFR Rate</div>
                    <div class="metric-value">{latest:.2f}%</div>
                    <div class="metric-delta {delta_class}">{delta:+.2f}%</div>
                </div>
                """, unsafe_allow_html=True)
        
        with col3:
            if not hy_spread.empty:
                latest = hy_spread.iloc[-1]["value"]
                prev = hy_spread.iloc[-2]["value"] if len(hy_spread) > 1 else latest
                delta = latest - prev
                # Inverse for spreads - lower is better
                delta_class = "negative" if delta >= 0 else "positive"
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">HY Spread</div>
                    <div class="metric-value">{latest:.0f} bps</div>
                    <div class="metric-delta {delta_class}">{delta:+.0f} bps</div>
                </div>
                """, unsafe_allow_html=True)
        
        with col4:
            if not us_m2.empty:
                latest = us_m2.iloc[-1]["value"]
                prev = us_m2.iloc[-2]["value"] if len(us_m2) > 1 else latest
                delta = (latest - prev) / prev * 100
                delta_class = "positive" if delta >= 0 else "negative"
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">US M2 Supply</div>
                    <div class="metric-value">${latest/1e3:.1f}T</div>
                    <div class="metric-delta {delta_class}">{delta:+.2f}%</div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        
        # Main chart - Fed Balance Sheet
        st.markdown('<div class="card-title">Federal Reserve Balance Sheet</div>', unsafe_allow_html=True)
        fig = create_chart(fed_assets, x="date", y="value", show_title=False)
        fig.update_layout(height=400)
        fig.update_yaxes(title_text="Millions USD")
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        
        # Two column charts
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown('<div class="card-title">Funding Rates — SOFR</div>', unsafe_allow_html=True)
            fig = create_chart(sofr, x="date", y="value", show_title=False)
            fig.update_layout(height=300)
            fig.update_yaxes(title_text="Rate %")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.markdown('<div class="card-title">Credit Spreads — US High Yield</div>', unsafe_allow_html=True)
            fig = create_chart(hy_spread, x="date", y="value", show_title=False)
            fig.update_layout(height=300)
            fig.update_yaxes(title_text="Spread (bps)")
            # Add fill to area
            fig.update_traces(fill='tozeroy', fillcolor='rgba(255,255,255,0.05)')
            st.plotly_chart(fig, use_container_width=True)
            
    except Exception as e:
        st.error(f"Error loading data: {e}")
        st.info("Make sure your FRED API key is valid and you have internet connectivity.")


def render_series_view(start_date: str, end_date: str):
    """View for exploring individual series."""
    
    all_series = get_all_series()
    
    # Group by source
    sources = {}
    for sid, cfg in all_series.items():
        source = cfg.get("source", "other")
        if source not in sources:
            sources[source] = []
        sources[source].append((sid, cfg.get("description", sid)))
    
    # Filters row
    col1, col2 = st.columns([1, 3])
    
    with col1:
        source_filter = st.selectbox("Source", ["All"] + list(sources.keys()))
    
    # Series selection
    if source_filter == "All":
        series_options = [(sid, cfg.get("description", sid)) for sid, cfg in all_series.items()]
    else:
        series_options = sources.get(source_filter, [])
    
    with col2:
        selected = st.selectbox(
            "Series",
            options=[s[0] for s in series_options],
            format_func=lambda x: next((s[1] for s in series_options if s[0] == x), x)
        )
    
    if selected:
        try:
            with st.spinner(""):
                df = fetch_series_cached(selected, start_date, end_date)
            
            if not df.empty:
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
                
                # Show metadata
                config = all_series.get(selected, {})
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown(f"""
                    <div class="stat-card">
                        <div class="stat-label">Source</div>
                        <div style="color: #fafafa; font-size: 1rem;">{config.get('source', 'N/A').upper()}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col2:
                    st.markdown(f"""
                    <div class="stat-card">
                        <div class="stat-label">Frequency</div>
                        <div style="color: #fafafa; font-size: 1rem;">{config.get('frequency', 'N/A').capitalize()}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col3:
                    st.markdown(f"""
                    <div class="stat-card">
                        <div class="stat-label">Unit</div>
                        <div style="color: #fafafa; font-size: 1rem;">{config.get('unit', 'N/A')}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
                
                # Chart
                st.markdown(f'<div class="card-title">{config.get("description", selected)}</div>', unsafe_allow_html=True)
                fig = create_chart(df, x="date", y="value", show_title=False)
                fig.update_layout(height=450)
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
                
                # Stats
                st.markdown('<div class="card-title">Statistics</div>', unsafe_allow_html=True)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Latest", f"{df['value'].iloc[-1]:,.2f}")
                col2.metric("Min", f"{df['value'].min():,.2f}")
                col3.metric("Max", f"{df['value'].max():,.2f}")
                col4.metric("Mean", f"{df['value'].mean():,.2f}")
                
                # Data table
                with st.expander("View Raw Data"):
                    st.dataframe(
                        df.tail(50).style.format({"value": "{:,.2f}"}),
                        use_container_width=True
                    )
            else:
                st.warning("No data available for selected series and date range.")
                
        except Exception as e:
            st.error(f"Error loading series: {e}")


def render_indices_view(start_date: str, end_date: str):
    """View for composite indices."""
    
    all_indices = get_all_indices()
    
    selected = st.selectbox(
        "Index",
        options=list(all_indices.keys()),
        format_func=lambda x: all_indices[x].get("description", x)
    )
    
    if selected:
        config = all_indices[selected]
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        
        # Index info
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Frequency</div>
                <div style="color: #fafafa; font-size: 1rem;">{config.get('frequency', 'N/A').capitalize()}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Method</div>
                <div style="color: #fafafa; font-size: 1rem;">{config.get('method', 'arithmetic').capitalize()}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col3:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Components</div>
                <div style="color: #fafafa; font-size: 1rem;">{len(config.get('components', []))}</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Show components
        with st.expander("View Components"):
            for i, comp in enumerate(config.get("components", [])):
                weight = comp.get('weight', 1.0)
                st.markdown(f"""
                <div style="display: flex; justify-content: space-between; padding: 0.75rem 0; border-bottom: 1px solid #262626;">
                    <span style="color: #fafafa;">{comp['series']}</span>
                    <span style="color: #737373; font-family: 'JetBrains Mono', monospace;">{weight:.2f}</span>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        
        try:
            with st.spinner(""):
                df = compute_index_cached(selected, start_date, end_date)
            
            if not df.empty:
                st.markdown(f'<div class="card-title">{config.get("description", selected)}</div>', unsafe_allow_html=True)
                fig = create_chart(df, x="date", y="value", show_title=False)
                fig.update_layout(height=450)
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
                
                # Add z-score view
                df_zscore = compute_zscore(df, window=60)
                
                st.markdown('<div class="card-title">Z-Score — 60-day Rolling</div>', unsafe_allow_html=True)
                
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=df_zscore["date"], 
                    y=df_zscore["zscore"],
                    mode="lines", 
                    name="Z-Score",
                    line={"color": "#ffffff", "width": 2},
                    hovertemplate="<b>%{x}</b><br>Z-Score: %{y:.2f}<extra></extra>"
                ))
                
                # Add reference lines
                fig2.add_hline(y=0, line_dash="dash", line_color="#525252", line_width=1)
                fig2.add_hline(y=2, line_dash="dot", line_color="#ef4444", line_width=1, 
                              annotation_text="+2σ", annotation_position="right")
                fig2.add_hline(y=-2, line_dash="dot", line_color="#22c55e", line_width=1,
                              annotation_text="-2σ", annotation_position="right")
                
                # Add shaded regions
                fig2.add_hrect(y0=2, y1=4, fillcolor="rgba(239, 68, 68, 0.1)", line_width=0)
                fig2.add_hrect(y0=-4, y1=-2, fillcolor="rgba(34, 197, 94, 0.1)", line_width=0)
                
                fig2.update_layout(**CHART_LAYOUT)
                fig2.update_layout(height=300, showlegend=False)
                fig2.update_yaxes(title_text="Z-Score")
                
                st.plotly_chart(fig2, use_container_width=True)
                
        except Exception as e:
            st.error(f"Error computing index: {e}")


def render_explorer(start_date: str, end_date: str):
    """Data explorer for comparing multiple series."""
    
    all_series = get_all_series()
    
    selected = st.multiselect(
        "Select Series to Compare",
        options=list(all_series.keys()),
        format_func=lambda x: all_series[x].get("description", x),
        max_selections=5
    )
    
    if selected:
        col1, col2 = st.columns([3, 1])
        with col2:
            normalize = st.checkbox("Normalize to 100", value=True)
        
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        
        try:
            with st.spinner(""):
                dfs = {}
                for sid in selected:
                    df = fetch_series_cached(sid, start_date, end_date)
                    if not df.empty:
                        dfs[sid] = df
            
            if dfs:
                # Combine for plotting
                combined = pd.DataFrame()
                for sid, df in dfs.items():
                    temp = df[["date", "value"]].copy()
                    if normalize and not temp.empty:
                        temp["value"] = temp["value"] / temp["value"].iloc[0] * 100
                    temp["series"] = all_series[sid].get("description", sid)
                    combined = pd.concat([combined, temp])
                
                st.markdown('<div class="card-title">Series Comparison</div>', unsafe_allow_html=True)
                fig = create_chart(combined, x="date", y="value", color="series", show_title=False)
                fig.update_layout(height=500)
                fig.update_layout(
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="left",
                        x=0,
                        bgcolor="rgba(0,0,0,0)"
                    )
                )
                
                if normalize:
                    fig.update_yaxes(title_text="Indexed (100 = Start)")
                    fig.add_hline(y=100, line_dash="dash", line_color="#525252", line_width=1)
                
                st.plotly_chart(fig, use_container_width=True)
                
        except Exception as e:
            st.error(f"Error loading data: {e}")
    else:
        st.markdown("""
        <div style="text-align: center; padding: 4rem 2rem; color: #525252;">
            <div style="font-size: 3rem; margin-bottom: 1rem;">◉</div>
            <div style="font-size: 1rem;">Select up to 5 series to compare</div>
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
