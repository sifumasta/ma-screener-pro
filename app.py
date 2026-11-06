# app.py - MA SCREENER PRO MOBILE (Streamlit)
# pip install streamlit pandas requests plotly
import streamlit as st
import requests, time
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="MA SCREENER PRO", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
BASE = "https://api.binance.com"
BASE_FALLBACK = "https://data-api.binance.vision"
HEADERS = {"User-Agent": "MA-Screener-Pro/1.0"}

# FIX STABLECOIN - sama macam PC version
EXCLUDE_BASE = {"USDT","USDC","DAI","FDUSD","TUSD","USDP","AEUR","EUR","XEUR","GBP","TRY","BRL","ARS","EURI","USD1","BFUSD","USDD","FRAX","LUSD","GUSD","PAXG","RLUSD","UUSD","USD","XUSD","USDJ","USDX","USDB","USDG","USDS","USDE","USDTB","USDF","SUSD","SUSDE","USDH","USD0","CUSD","VUSD","EUSD","BUSD","AUSD","MUSD","OUSD","ZUSD","DUSD","U"}
BLOCK_SYMBOL = {"UUSDT", "UUSDUSDT", "RLUSDUSDT", "USD1USDT", "USDEUSDT", "USDSUSDT"}

def fmt_price(v):
    try: v = float(v)
    except: return "0"
    if v == 0: return "0.000000"
    if v >= 1000: return f"{v:,.2f}"
    if v >= 100: return f"{v:,.3f}"
    if v >= 10: return f"{v:,.4f}"
    if v >= 1: return f"{v:,.5f}"
    if v >= 0.01: return f"{v:,.6f}"
    if v >= 0.0001: return f"{v:,.8f}"
    return f"{v:.10f}"

def binance_get(path, params=None):
    for base in [BASE, BASE_FALLBACK]:
        try:
            r = requests.get(f"{base}{path}", params=params, headers=HEADERS, timeout=15)
            if r.status_code == 200: return r.json()
        except: continue
    return None

def get_usdt_symbols():
    r = binance_get("/api/v3/exchangeInfo")
    if not r or "symbols" not in r: return []
    out = []
    for s in r['symbols']:
        if s['status'] != 'TRADING' or s['quoteAsset'] != 'USDT' or not s['isSpotTradingAllowed']: continue
        sym = s['symbol']
        if sym in BLOCK_SYMBOL: continue
        base = sym[:-4] if sym.endswith("USDT") else sym
        if base in EXCLUDE_BASE: continue
        if base.startswith("UUSD") or base.startswith("RLUSD") or base.startswith("USD"): continue
        out.append(sym)
    return sorted(out)

def calc_dca(symbol, jarak, vol, diff_fibo, want):
    if want == "Atas MA":
        if jarak >= 100: return 10, "TIER 3 - JANGAN DCA"
        elif jarak >= 20: return 30, "TIER 3 - TUNGGU"
        else: return 45, "TIER 2 - DCA SIKIT"
    score = 50
    if -35 <= jarak <= -5: score += 25
    elif -60 <= jarak < -35: score += 10
    elif jarak > -5: score += 15
    elif jarak < -60: score -= 15
    if vol >= 100_000_000: score += 20
    elif vol >= 50_000_000: score += 15
    elif vol >= 20_000_000: score += 10
    elif vol < 12_000_000: score -= 10
    if diff_fibo <= 3: score += 5
    blue = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","LINKUSDT","AAVEUSDT","ADAUSDT","AVAXUSDT","DOGEUSDT","LTCUSDT"]
    if symbol in blue: score += 5
    score = max(0, min(100, int(score)))
    if score >= 70: tier = f"TIER 1 - DCA UTAMA ({score})"
    elif score >= 45: tier = f"TIER 2 - DCA SIKIT ({score})"
    else: tier = f"TIER 3 - TUNGGU ({score})"
    return score, tier

def calc_tp(symbol, jarak, vol, price, hi, lo):
    score = 40
    if jarak >= 150: score += 40
    elif jarak >= 100: score += 30
    elif jarak >= 50: score += 20
    elif jarak >= 20: score += 10
    elif jarak < 20: score -= 10
    if vol >= 100_000_000: score += 15
    elif vol >= 50_000_000: score += 10
    elif vol >= 20_000_000: score += 5
    if hi > 0 and lo > 0:
        rng = hi - lo
        if rng > 0:
            pos = (price - lo) / rng * 100
            if pos >= 95: score += 15
            elif pos >= 85: score += 10
            elif pos >= 75: score += 5
    blue = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","LINKUSDT","AAVEUSDT","ADAUSDT","AVAXUSDT","DOGEUSDT","LTCUSDT"]
    if symbol in blue: score += 5
    score = max(0, min(100, int(score)))
    if score >= 75: tier = f"TIER 1 - JUAL UTAMA ({score})"
    elif score >= 50: tier = f"TIER 2 - JUAL SIKIT ({score})"
    else: tier = f"TIER 3 - HOLD DULU ({score})"
    return score, tier

def do_scan(mode, ma_len, tf, want, min_vol):
    if mode == "TAKE PROFIT": want = "Atas MA"
    syms = get_usdt_symbols()
    r = binance_get("/api/v3/ticker/24hr")
    tickers = {x['symbol']: x for x in r} if isinstance(r, list) else {}
    results = []
    bar = st.progress(0, text="Scanning...")
    for i, sym in enumerate(syms):
        if i % 20 == 0: bar.progress(min(i/len(syms), 1.0), text=f"Scanning {i}/{len(syms)} - {sym}")
        t = tickers.get(sym)
        if not t: continue
        try: vol = float(t['quoteVolume'])
        except: continue
        if vol < min_vol: continue
        kl = binance_get("/api/v3/klines", params={"symbol": sym, "interval": tf, "limit": 250})
        if not isinstance(kl, list) or len(kl) < ma_len: continue
        closes = [float(x[4]) for x in kl]; highs = [float(x[2]) for x in kl]; lows = [float(x[3]) for x in kl]
        price = closes[-1]; ma = sum(closes[-ma_len:]) / ma_len; jarak = (price - ma)/ma*100
        # FIX STABLECOIN: Buang coin lekat $1.00
        if 0.98 <= price <= 1.02 and abs(jarak) < 1.0: continue
        is_atas = price > ma
        if want == "Atas MA" and not is_atas: continue
        if want == "Bawah MA" and is_atas: continue
        hi = max(highs); lo = min(lows)
        fib786 = hi - 0.786*(hi-lo) if hi != lo else 0
        diff_fibo = abs(price-fib786)/fib786*100 if fib786 else 999
        if diff_fibo <= 3: fib_sig = f"DEKAT 78.6% ({diff_fibo:.1f}%)"
        elif price < fib786: fib_sig = "Bawah 78.6% - Jackpot Zone" if want != "Atas MA" else f"Bawah 78.6% tapi Atas MA ({diff_fibo:.0f}%)"
        else: fib_sig = f"Jauh 78.6% ({diff_fibo:.0f}%)"
        if mode == "TAKE PROFIT":
            score, tier = calc_tp(sym, jarak, vol, price, hi, lo)
            if jarak >= 100: fib_sig = f"OVER-EXTENDED +{jarak:.0f}% - TP ZONE"
            elif jarak >= 50: fib_sig = f"Jauh dari MA +{jarak:.0f}% - PARTIAL TP"
        else:
            score, tier = calc_dca(sym, jarak, vol, diff_fibo, want)
        results.append({"Symbol": sym, "Price": price, "Price Str": fmt_price(price), "MA": ma, "MA Str": fmt_price(ma), "Jarak %": round(jarak,2), "Fibo 78.6%": fmt_price(fib786), "Fibo Signal": fib_sig, "Vol 24h": vol, "Score": score, "Tier": tier})
        time.sleep(0.02)
    bar.empty()
    if mode == "TAKE PROFIT": results = sorted(results, key=lambda x: x["Score"], reverse=True)
    elif want == "Bawah MA": results = sorted(results, key=lambda x: x["Score"], reverse=True)
    else: results = sorted(results, key=lambda x: x["Jarak %"], reverse=True)
    return results

# --- UI MOBILE ---
st.markdown("## 📈 MA SCREENER PRO - Mobile")
st.caption(f"Binance Spot USDT | {datetime.now().strftime('%d %b %Y, %H:%M:%S')}")

c1, c2 = st.columns(2)
with c1:
    mode = st.selectbox("MODE", ["DCA", "TAKE PROFIT"], index=0)
with c2:
    ma_len = st.selectbox("MA", [20, 50, 100, 200], index=3)
c3, c4 = st.columns(2)
with c3:
    tf = st.selectbox("TF", ["15m","1h","4h","1d","1w"], index=4)
with c4:
    pos = st.selectbox("Price", ["Bawah MA","Atas MA"], index=0 if mode=="DCA" else 1)
min_vol = st.number_input("Min Vol $", value=10000000, step=1000000)

if st.button("🔍 SCAN NOW", type="primary", use_container_width=True):
    with st.spinner("Scanning Binance..."):
        res = do_scan(mode, ma_len, tf, pos, min_vol)
        st.session_state["res"] = res
        st.session_state["meta"] = (mode, ma_len, tf, pos)

if "res" in st.session_state and st.session_state["res"]:
    res = st.session_state["res"]
    mode_s, ma_s, tf_s, pos_s = st.session_state["meta"]
    t1 = [r for r in res if (r["Score"]>=75 if mode_s=="TAKE PROFIT" else r["Score"]>=70)]
    t2 = [r for r in res if (50 <= r["Score"] < 75 if mode_s=="TAKE PROFIT" else 45 <= r["Score"] < 70)]
    t3 = [r for r in res if (r["Score"]<50 if mode_s=="TAKE PROFIT" else r["Score"]<45)]
    a,b,c = st.columns(3)
    a.metric("TIER 1", len(t1)); b.metric("TIER 2", len(t2)); c.metric("TIER 3", len(t3))
    if t1:
        top3 = ", ".join([r['Symbol'] + " (" + str(r['Score']) + ")" for r in t1[:3]])
st.success("TOP: " + top3)
    df = pd.DataFrame(res)[["Symbol","Price Str","MA Str","Jarak %","Fibo 78.6%","Fibo Signal","Vol 24h","Tier"]]
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download CSV", df.to_csv(index=False), "screener.csv", "text/csv", use_container_width=True)
    # Chart
    st.markdown("### 📊 Chart")
    sym_list = [r["Symbol"] for r in res]
    sel = st.selectbox("Pilih Coin untuk Chart", sym_list)
    if sel:
        kl = binance_get("/api/v3/klines", params={"symbol": sel, "interval": tf_s, "limit": 120})
        if isinstance(kl, list) and len(kl) > 10:
            dates = [datetime.fromtimestamp(int(x[0])/1000) for x in kl]
            closes = [float(x[4]) for x in kl]; opens=[float(x[1]) for x in kl]; highs=[float(x[2]) for x in kl]; lows=[float(x[3]) for x in kl]
            ma_vals = [sum(closes[i-ma_s+1:i+1])/ma_s if i>=ma_s-1 else None for i in range(len(closes))]
            hi = max(highs); lo = min(lows); fib786 = hi - 0.786*(hi-lo); fib618 = hi - 0.618*(hi-lo)
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=dates, open=opens, high=highs, low=lows, close=closes, name=sel))
            fig.add_trace(go.Scatter(x=dates, y=ma_vals, mode="lines", name=f"MA {ma_s}", line=dict(color="orange", dash="dash")))
            fig.add_hline(y=fib786, line_color="green", annotation_text=f"Fibo 78.6% {fmt_price(fib786)}")
            fig.add_hline(y=fib618, line_color="yellow", annotation_text=f"Fibo 61.8% {fmt_price(fib618)}")
            if mode_s == "TAKE PROFIT":
                fig.add_hline(y=hi + 0.272*(hi-lo), line_color="magenta", annotation_text="TP 127.2%")
                fig.add_hline(y=hi + 0.618*(hi-lo), line_color="red", annotation_text="TP 161.8%")
            fig.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10,r=10,t=30,b=10))
            st.plotly_chart(fig, use_container_width=True)
            row = next(r for r in res if r["Symbol"]==sel)
            st.info(f"{sel} | Price ${row['Price Str']} | MA {ma_s} ${row['MA Str']} | Jarak {row['Jarak %']}% | {row['Tier']}")
else:
    st.info("Pilih MODE / MA / TF, tekan SCAN NOW. TIER 1 = DCA UTAMA / JUAL UTAMA.")
