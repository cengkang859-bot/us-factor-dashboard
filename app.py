"""
美股因子选股 — 云部署可视化仪表盘
====================================
基于 Streamlit + Yahoo Finance 实时数据

部署方式:
  1. 推送到 GitHub
  2. 连接 Streamlit Cloud (免费)
  3. 自动更新，无需服务器

功能:
  - 实时信号面板 (多空双向)
  - 因子热力图
  - 回测权益曲线
  - 个股表现排行
  - 一键刷新生效
"""

import json, os, sys, time, math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="US Stock Factor Model",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== CONFIG ==========
STOCKS = {
    "AMD": "AMDON_USDT", "HOOD": "HOODON_USDT", "TSLA": "TSLAON_USDT",
    "NVDA": "NVDAON_USDT", "COIN": "COINON_USDT", "BABA": "BABAON_USDT",
    "PLTR": "PLTRON_USDT", "JPM": "JPMON_USDT", "KO": "KOON_USDT",
    "LLY": "LLYON_USDT", "PG": "PGON_USDT", "NFLX": "NFLXON_USDT",
    "SBUX": "SBUXON_USDT", "LMT": "LMTON_USDT", "V": "VON_USDT",
    "CVX": "CVXON_USDT", "UNH": "UNHON_USDT", "SPY": "SPYON_USDT", "QQQ": "QQQON_USDT",
}

SHORT_TOKENS = {
    "HOOD": "HOODX_USDT", "TSLA": "TSLA3S_USDT", "NVDA": "NVDA3S_USDT",
    "COIN": "COINX_USDT", "BABA": "BABA3S_USDT", "JPM": "JPM3S_USDT",
    "KO": "KOX_USDT", "LLY": "LLYX_USDT", "PG": "PGX_USDT",
    "NFLX": "NFLXX_USDT", "UNH": "UNHX_USDT", "SPY": "SPY3S_USDT", "QQQ": "QQQ3S_USDT",
}

SHORT_LEVERAGE = {
    "HOOD": 1.5, "TSLA": 3, "NVDA": 3, "COIN": 1.5, "BABA": 3, "JPM": 3,
    "KO": 1.5, "NFLX": 1.5, "PG": 1.5, "UNH": 1.5, "LLY": 1.5, "SPY": 3, "QQQ": 3,
}

FACTOR_WEIGHTS = {"MOM": 0.30, "RVOL": 0.30, "GAP": 0.10, "VWAP": 0.13, "RSI": 0.05, "TREND": 0.12}
YAHOO_HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}

# ========== DATA ==========

@st.cache_data(ttl=300)  # 5 minute cache
def fetch_all_stocks() -> Dict[str, list]:
    results = {}
    for ticker in STOCKS:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"range": "5d", "interval": "15m", "includePrePost": "false"}
        try:
            r = requests.get(url, params=params, headers=YAHOO_HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json()
                result = data["chart"]["result"][0]
                timestamps = result["timestamp"]
                quotes = result["indicators"]["quote"][0]
                candles = []
                for i, ts in enumerate(timestamps):
                    o, c = quotes["open"][i], quotes["close"][i]
                    if o is None or c is None: continue
                    candles.append({
                        "ts": int(ts), "open": float(o),
                        "high": float(quotes["high"][i] or o),
                        "low": float(quotes["low"][i] or o),
                        "close": float(c), "volume": float(quotes["volume"][i] or 0),
                    })
                results[ticker] = candles
        except:
            pass
        time.sleep(0.3)
    return results

@st.cache_data(ttl=3600)
def fetch_history_data(days: int = 60) -> Dict[str, list]:
    results = {}
    for ticker in STOCKS:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"range": "1mo", "interval": "15m", "includePrePost": "false"}
        try:
            r = requests.get(url, params=params, headers=YAHOO_HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json()
                result = data["chart"]["result"][0]
                timestamps = result["timestamp"]
                quotes = result["indicators"]["quote"][0]
                candles = []
                for i, ts in enumerate(timestamps):
                    o, c = quotes["open"][i], quotes["close"][i]
                    if o is None or c is None: continue
                    candles.append({
                        "ts": int(ts), "open": float(o),
                        "high": float(quotes["high"][i] or o),
                        "low": float(quotes["low"][i] or o),
                        "close": float(c), "volume": float(quotes["volume"][i] or 0),
                    })
                results[ticker] = candles
        except:
            pass
        time.sleep(0.3)
    return results

# ========== FACTOR ENGINE ==========

def compute_atr(candles, period=14):
    if len(candles) < period + 1: return 0
    trs = [max(c['high']-c['low'], abs(c['high']-c2['close']), abs(c['low']-c2['close']))
           for c, c2 in zip(candles[1:], candles[:-1])]
    return sum(trs[-period:]) / period

def compute_vwap(candles, lookback=20):
    n = min(lookback, len(candles))
    tpv = tv = 0.0
    for c in candles[-n:]:
        typical = (c['high'] + c['low'] + c['close']) / 3
        tpv += typical * c['volume']
        tv += c['volume']
    return tpv / tv if tv > 0 else candles[-1]['close']

def compute_rsi(candles, period=14):
    if len(candles) < period + 1: return 50
    closes = [c['close'] for c in candles]
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100
    return 100 - 100 / (1 + avg_gain / avg_loss)

def compute_all_factors(candles):
    if len(candles) < 48: return {}
    closes = [c['close'] for c in candles]
    n = len(closes); cc = closes[-1]
    gap = (cc - closes[-2]) / closes[-2] if n >= 2 else 0
    mom6 = (closes[-1] - closes[-6]) / closes[-6] if n >= 7 else 0
    mom12 = (closes[-1] - closes[-12]) / closes[-12] if n >= 13 else mom6
    mom24 = (closes[-1] - closes[-24]) / closes[-24] if n >= 25 else mom12
    mom_score = mom6 * 0.4 + mom12 * 0.35 + mom24 * 0.25
    volumes = [c['volume'] for c in candles]
    vol_ma20 = sum(volumes[-20:]) / 20 if n >= 20 else sum(volumes) / max(len(volumes), 1)
    rvol = volumes[-1] / vol_ma20 if vol_ma20 > 0 else 1.0
    vwap_v = compute_vwap(candles, 20)
    vwap_dist = (cc - vwap_v) / vwap_v if vwap_v > 0 else 0
    rsi14 = compute_rsi(candles, 14)
    if 40 <= rsi14 <= 70: rsi_score = 8.0
    elif rsi14 < 30: rsi_score = 5.0
    elif rsi14 > 80: rsi_score = 2.0
    else: rsi_score = 4.0
    adx = 20  # Simplified
    return {"GAP": gap, "MOM": mom_score, "RVOL": rvol, "VWAP": vwap_dist,
            "RSI": rsi_score, "TREND": adx, "close": cc, "atr": compute_atr(candles, 14),
            "vwap_v": vwap_v, "rsi_val": rsi14}

def normalize_factors(all_factors):
    pairs = list(all_factors.keys())
    factor_names = ["MOM", "RVOL", "GAP", "VWAP", "RSI", "TREND"]
    fv = {f: {} for f in factor_names}
    for p, fac in all_factors.items():
        for f in factor_names:
            fv[f][p] = fac.get(f, 0)
    normalized = {}
    for p, fac in all_factors.items():
        nf = {}
        for f in factor_names:
            vs = list(fv[f].values())
            if len(vs) < 2: nf[f] = 50; continue
            mn, mx = min(vs), max(vs)
            if f in ["GAP", "VWAP", "MOM"]:
                raw = fac.get(f, 0)
                if mx - mn < 1e-10: nf[f] = 50
                else:
                    mid, hr = (mn + mx) / 2, (mx - mn) / 2
                    nf[f] = max(0, min(100, 50 + (raw - mid) / (hr if hr > 1e-10 else 1) * 50))
            else:
                raw = fac.get(f, 0)
                nf[f] = max(0, min(100, (raw - mn) / (mx - mn) * 100)) if mx - mn > 1e-10 else 50
        nf["close"] = fac.get("close", 0); nf["atr"] = fac.get("atr", 0)
        nf["vwap_v"] = fac.get("vwap_v", 0); nf["rsi_val"] = fac.get("rsi_val", 50)
        normalized[p] = nf
    return normalized

def get_signals(all_factors):
    normalized = normalize_factors(all_factors)
    rankings = []
    for p, fac in normalized.items():
        score = sum(fac.get(f, 50) * FACTOR_WEIGHTS[f] for f in FACTOR_WEIGHTS)
        rankings.append((p, score, fac))
    rankings.sort(key=lambda x: x[1], reverse=True)

    longs = []
    for ticker, score, fac in rankings:
        if score < 30: continue
        if fac.get('MOM', 0) * max(all_factors[ticker].get('MOM', 0)/abs(all_factors[ticker].get('MOM', 0) or 1), 0) > 0:
            pass
        raw_fac = all_factors.get(ticker, {})
        if raw_fac.get('MOM', 0) > 0 and raw_fac.get('VWAP', 0) > -0.003:
            longs.append((ticker, score, fac))
        if len(longs) >= 3: break

    shorts = []
    for ticker, score, fac in reversed(rankings):
        if ticker not in SHORT_TOKENS: continue
        raw_fac = all_factors.get(ticker, {})
        if raw_fac.get('MOM', 0) < 0 and raw_fac.get('VWAP', 0) < 0:
            shorts.append((ticker, score, fac))
        if len(shorts) >= 3: break

    return rankings, longs, shorts, normalized

def run_backtest():
    """Cacheable backtest computation"""
    hist = fetch_history_data(60)
    tickers = list(hist.keys())
    ref_ts = {c['ts'] for c in hist[tickers[0]]}
    for t in tickers[1:]:
        ref_ts &= {c['ts'] for c in hist[t]}
    common_ts = sorted(ref_ts)
    n = min(len(common_ts), 500)
    step = 4
    long_ret, short_ret = [], []
    long_by_t = {}; short_by_t = {}

    for i in range(48, n - 1, step):
        ft = {}
        for ticker in tickers:
            tm = {c['ts']: c for c in hist[ticker]}
            w = [tm[ts] for ts in common_ts[max(0, i-48):i] if ts in tm]
            if len(w) < 48: continue
            fac = compute_all_factors(w)
            if fac: ft[ticker] = fac
        if len(ft) < 3: continue

        norm = normalize_factors(ft)
        rks = []
        for p, fac in norm.items():
            sc = sum(fac.get(f, 50) * FACTOR_WEIGHTS[f] for f in FACTOR_WEIGHTS)
            rks.append((p, sc))
        rks.sort(key=lambda x: x[1], reverse=True)

        # LONG
        lq = []
        for t, sc in rks:
            if sc < 30: continue
            raw = ft.get(t, {})
            if raw.get('MOM', 0) > 0 and raw.get('VWAP', 0) > -0.003:
                lq.append((t, sc))
            if len(lq) >= 3: break
        # SHORT
        sq = []
        for t, sc in reversed(rks):
            if t not in SHORT_TOKENS: continue
            raw = ft.get(t, {})
            if raw.get('MOM', 0) < 0 and raw.get('VWAP', 0) < 0:
                sq.append((t, sc))
            if len(sq) >= 3: break

        fi = min(i + step, n - 1)

        for t, sc in lq:
            tm = {c['ts']: c for c in hist[t]}
            if common_ts[i] not in tm or common_ts[fi] not in tm: continue
            en = tm[common_ts[i]]['close']; ex = tm[common_ts[fi]]['close']
            ret = (ex - en) / en
            long_ret.append(ret)
            long_by_t.setdefault(t, []).append(ret)

        for t, sc in sq:
            tm = {c['ts']: c for c in hist[t]}
            if common_ts[i] not in tm or common_ts[fi] not in tm: continue
            en = tm[common_ts[i]]['close']; ex = tm[common_ts[fi]]['close']
            lev = SHORT_LEVERAGE.get(t, 3)
            ret = (en - ex) / en * lev
            short_ret.append(ret)
            short_by_t.setdefault(t, []).append(ret)

    return long_ret, short_ret, long_by_t, short_by_t


# ========== UI ==========

st.title("📊 US Stock Factor Model — Long/Short")
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# Sidebar
st.sidebar.header("⚙️ Controls")
refresh = st.sidebar.button("🔄 Refresh Data")
st.sidebar.markdown("---")

# Market status
now = datetime.now()
if now.weekday() >= 5:
    st.sidebar.warning("🏖️ Weekend — Market Closed")
elif now.hour < 13 or now.hour > 20:
    st.sidebar.info("🌙 Outside Market Hours (9:30-16:00 EST)")
else:
    st.sidebar.success("🟢 Market Open")

st.sidebar.markdown("### Factor Weights")
for f, w in FACTOR_WEIGHTS.items():
    st.sidebar.progress(w, text=f"{f} ({w*100:.0f}%)")

with st.spinner("Fetching live data..."):
    data = fetch_all_stocks()

# Compute factors and signals
all_factors = {}
for ticker, candles in data.items():
    fac = compute_all_factors(candles)
    if fac: all_factors[ticker] = fac

# ========== MAIN SIGNAL PANEL ==========
st.header("🎯 Live Signals")

if all_factors:
    rankings, longs, shorts, normalized = get_signals(all_factors)
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 LONG (Top 3)")
        if longs:
            for ticker, score, fac in longs:
                raw = all_factors.get(ticker, {})
                px = raw.get('close', 0)
                sl = px - raw.get('atr', 0) * 1.5
                tp = px + raw.get('atr', 0) * 3
                gate = STOCKS.get(ticker, '?')
                with st.container():
                    c1, c2, c3 = st.columns([2, 1, 2])
                    with c1:
                        st.markdown(f"**{ticker}** `{gate}`")
                        st.caption(f"Score: {score:.0f}")
                    with c2:
                        st.metric("Price", f"${px:.2f}")
                    with c3:
                        st.metric("SL/TP", f"${sl:.1f} / ${tp:.1f}")
                    st.progress(score / 100, text="")
        else:
            st.info("No long signals")

    with col2:
        st.subheader("📉 SHORT (Bottom 3)")
        if shorts:
            for ticker, score, fac in shorts:
                raw = all_factors.get(ticker, {})
                px = raw.get('close', 0)
                sl_up = px + raw.get('atr', 0) * 1.5
                tp_dn = px - raw.get('atr', 0) * 3
                gate = SHORT_TOKENS.get(ticker, '?')
                lev = SHORT_LEVERAGE.get(ticker, 3)
                with st.container():
                    c1, c2, c3 = st.columns([2, 1, 2])
                    with c1:
                        st.markdown(f"**{ticker}** `{gate}` x{lev}")
                        st.caption(f"Score: {score:.0f}")
                    with c2:
                        st.metric("Price", f"${px:.2f}")
                    with c3:
                        st.metric("SL/TP", f"${sl_up:.1f} / ${tp_dn:.1f}")
                    st.progress(score / 100, text="")
        else:
            st.info("No short signals")
else:
    st.error("No data available — Yahoo Finance rate limited. Try again later.")

# ========== FULL RANKINGS ==========
st.header("📋 Full Rankings")
if all_factors:
    df_rows = []
    for ticker, score, fac in rankings:
        raw = all_factors.get(ticker, {})
        px = raw.get('close', 0)
        long_short = ""
        if any(t == ticker for t, _, _ in longs): long_short = "📈 LONG"
        if any(t == ticker for t, _, _ in shorts): long_short = "📉 SHORT"
        df_rows.append({
            "Signal": long_short, "Ticker": ticker, "Score": f"{score:.0f}",
            "Price": f"${px:.2f}", "MOM": f'{fac.get("MOM", 0):.0f}',
            "RVOL": f'{fac.get("RVOL", 0):.0f}', "GAP": f'{fac.get("GAP", 0):.0f}',
            "VWAP": f'{fac.get("VWAP", 0):.0f}', "RSI": f'{fac.get("RSI", 0):.0f}',
            "TREND": f'{fac.get("TREND", 0):.0f}',
            " VWAP $": f'${raw.get("vwap_v", 0):.2f}',
        })
    df = pd.DataFrame(df_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No data available")

# ========== FACTOR HEATMAP ==========
st.header("🔥 Factor Heatmap")
if all_factors:
    heat_data = []
    for ticker in STOCKS:
        if ticker in all_factors:
            raw = all_factors[ticker]
            row = {"Ticker": ticker}
            for f in FACTOR_WEIGHTS:
                row[f] = raw.get(f, 50)
            heat_data.append(row)
    if heat_data:
        heat_df = pd.DataFrame(heat_data).set_index("Ticker")
        fig = px.imshow(heat_df.values,
                        x=heat_df.columns,
                        y=heat_df.index,
                        color_continuous_scale="RdYlGn",
                        aspect="auto",
                        labels={"x": "Factor", "y": "Stock", "color": "Score"},
                        title="Factor Scores (0-100)")
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

# ========== BACKTEST EQUITY CURVE ==========
st.header("📈 Backtest Equity Curve (22-day)")

with st.spinner("Computing backtest..."):
    long_ret, short_ret, long_by_t, short_by_t = run_backtest()

if long_ret or short_ret:
    # Build equity curves
    eq_long = [10000]
    for r in long_ret: eq_long.append(eq_long[-1] * (1 + r))
    eq_short = [10000]
    for r in short_ret: eq_short.append(eq_short[-1] * (1 + r))
    eq_combined = [10000]
    # Interleave long+short (they happen at the same time)
    for i in range(min(len(long_ret), len(short_ret))):
        combined_r = (long_ret[i] + short_ret[i]) / 2 if len(long_ret) > i and len(short_ret) > i else (long_ret[i] if len(long_ret) > i else short_ret[i])
        eq_combined.append(eq_combined[-1] * (1 + combined_r))
    # For remainder
    for r in long_ret[len(short_ret):]:
        eq_combined.append(eq_combined[-1] * (1 + r / 2))
    for r in short_ret[len(long_ret):]:
        eq_combined.append(eq_combined[-1] * (1 + r / 2))

    fig = go.Figure()
    fig.add_trace(go.Scatter(y=eq_long, mode='lines', name='Long Only', line=dict(color='green', width=2)))
    fig.add_trace(go.Scatter(y=eq_short, mode='lines', name='Short Only', line=dict(color='red', width=2)))
    fig.add_trace(go.Scatter(y=eq_combined, mode='lines', name='Long+Short', line=dict(color='blue', width=3)))
    fig.update_layout(height=400, title="Portfolio Equity ($10,000 start)",
                     yaxis_title="Portfolio Value ($)", xaxis_title="Trade #")
    st.plotly_chart(fig, use_container_width=True)

    # Summary stats
    col1, col2, col3, col4 = st.columns(4)
    def stats(returns, label):
        if not returns: return 0, 0, 0, 0
        rs = returns; win = [r for r in rs if r > 0]
        pf = abs(sum(win) / sum([r for r in rs if r <= 0])) if any(r <= 0 for r in rs) else float('inf')
        total = (np.prod([1+r for r in rs]) - 1) * 100
        wr = len(win) / len(rs) * 100
        return pf, total, wr, len(rs)

    pf_l, tr_l, wr_l, nt_l = stats(long_ret, "Long")
    pf_s, tr_s, wr_s, nt_s = stats(short_ret, "Short")
    combined_all = long_ret + short_ret
    pf_c, tr_c, wr_c, nt_c = stats(combined_all, "Combined")

    with col1:
        st.metric("Long PF", f"{pf_l:.2f}", f"{tr_l:+.1f}%")
    with col2:
        st.metric("Short PF", f"{pf_s:.2f}", f"{tr_s:+.1f}%")
    with col3:
        st.metric("Combined PF", f"{pf_c:.2f}", f"{tr_c:+.1f}%")
    with col4:
        st.metric("Total Trades", f"{nt_l + nt_s}")

    # Performance by ticker
    st.subheader("By Ticker — Long")
    if long_by_t:
        rows = []
        for t, rs in sorted(long_by_t.items(), key=lambda x: sum(x[1]), reverse=True):
            rows.append({"Ticker": t, "Trades": len(rs),
                        "Return": f"{sum(rs)*100:+.1f}%",
                        "Win Rate": f"{len([r for r in rs if r>0])/len(rs)*100:.0f}%"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.subheader("By Ticker — Short")
    if short_by_t:
        rows = []
        for t, rs in sorted(short_by_t.items(), key=lambda x: sum(x[1]), reverse=True):
            rows.append({"Ticker": t, "Trades": len(rs),
                        "Return": f"{sum(rs)*100:+.1f}%",
                        "Win Rate": f"{len([r for r in rs if r>0])/len(rs)*100:.0f}%"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ========== FOOTER ==========
st.markdown("---")
st.caption("Data: Yahoo Finance | Execution: Gate.io | v3.0 Long/Short Factor Model")
