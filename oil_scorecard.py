"""
WTI crude oil: supply/demand scorecard + speculative positioning + directional view.

Data (all real, publicly sourced):
  - WTI & Brent futures prices                          -> Yahoo Finance (CL=F, BZ=F)
  - US commercial crude oil stocks ex-SPR (weekly)       -> EIA
  - US weekly field production of crude oil              -> EIA
  - CFTC Disaggregated Commitments of Traders, WTI-Physical
    (NYMEX code 067651), Managed Money net positioning    -> CFTC bulk history files

Methodology:
  1. Build 4 standardized (z-score) indicators, each expressing "bullish
     pressure" in the same direction (positive = supportive of higher
     prices):
       a. Inventory z-score (negative of stocks vs trailing 5y seasonal
          average: low stocks vs season = bullish)
       b. Production growth z-score (negative of YoY production growth:
          slowing/falling US supply = bullish)
       c. Managed Money net positioning z-score, AS A CONTRARIAN signal
          (extreme crowded long = bearish going forward, extreme crowded
          short = bullish going forward) -> sign flipped
       d. WTI-Brent spread z-score (narrower WTI discount vs Brent =
          relatively tighter US market = bullish for WTI specifically)
  2. Composite score = equal-weighted average of the 4 z-scores.
  3. Train/test split (70/30): z-score means/stds are computed expanding
     (using only data up to each date), so there is no look-ahead even
     within "train". The split is used to check whether the composite
     score's explanatory power holds out-of-sample.
  4. Test the composite score's explanatory power: regress forward 4-week
     WTI returns on the composite score (lagged), on TRAIN and TEST
     separately, and report the sign/significance honestly.
  5. Current view: read off the latest value of each indicator and the
     composite, and state the directional view implied - explicitly
     flagged as a view, not a guaranteed forecast.
"""

import numpy as np
import pandas as pd
import yfinance as yf

FORWARD_WINDOW = 20     # trading days (~4 weeks) forward return horizon
TRAIN_FRAC = 0.70
EXPANDING_MIN_PERIODS = 52  # ~1 year of weekly data before z-scores start


def load_cftc_positioning(path="rawdata/cftc_wti_clean.csv"):
    df = pd.read_csv(path, parse_dates=["Report_Date_as_YYYY-MM-DD"])
    df = df.rename(columns={"Report_Date_as_YYYY-MM-DD": "date"})
    df = df[["date", "net_mm_pct_oi"]].sort_values("date").set_index("date")
    return df


def load_eia_series(path, sheet="Data 1", skiprows=2, value_name="value"):
    df = pd.read_excel(path, sheet_name=sheet, skiprows=skiprows)
    df.columns = ["date", value_name]
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def load_prices():
    px = yf.download(["CL=F", "BZ=F"], period="10y", progress=False)["Close"]
    px = px.rename(columns={"CL=F": "WTI", "BZ=F": "Brent"}).dropna()
    return px


def expanding_zscore(s, min_periods=EXPANDING_MIN_PERIODS):
    mean = s.expanding(min_periods=min_periods).mean()
    std = s.expanding(min_periods=min_periods).std()
    return (s - mean) / std


def seasonal_inventory_deviation(stocks_weekly):
    """Deviation of stocks from trailing 5y same-week average, as % of that average."""
    s = stocks_weekly["stocks_kbbl"]
    week = s.index.isocalendar().week
    df = pd.DataFrame({"value": s, "week": week})
    seasonal_avg = df.groupby("week")["value"].transform(
        lambda x: x.rolling(5, min_periods=2).mean()
    )
    dev_pct = (df["value"] - seasonal_avg) / seasonal_avg
    return dev_pct


def build_indicators():
    cftc = load_cftc_positioning()
    stocks = load_eia_series("rawdata/wti_stocks.xls", value_name="stocks_kbbl")
    prod = load_eia_series("rawdata/wti_production.xls", value_name="prod_kbd")
    px = load_prices()

    # weekly resample of daily prices to align with weekly fundamentals
    px_w = px.resample("W-FRI").last()

    inv_dev = seasonal_inventory_deviation(stocks)
    prod_yoy = prod["prod_kbd"].pct_change(52)
    wti_brent_spread = px_w["WTI"] - px_w["Brent"]

    idx = cftc.index.union(inv_dev.index).union(prod_yoy.index).union(wti_brent_spread.index)
    idx = idx.sort_values()

    panel = pd.DataFrame(index=idx)
    panel["inv_dev"] = inv_dev.reindex(idx).ffill()
    panel["prod_yoy"] = prod_yoy.reindex(idx).ffill()
    panel["net_mm_pct_oi"] = cftc["net_mm_pct_oi"].reindex(idx).ffill()
    panel["wti_brent_spread"] = wti_brent_spread.reindex(idx).ffill()
    panel["wti_price"] = px_w["WTI"].reindex(idx).ffill()
    panel = panel.dropna()

    # bullish-pressure z-scores, all oriented so that +1 = bullish for price
    z_inv = -expanding_zscore(panel["inv_dev"])              # low stocks vs season = bullish
    z_prod = -expanding_zscore(panel["prod_yoy"])            # falling supply growth = bullish
    z_pos = -expanding_zscore(panel["net_mm_pct_oi"])        # contrarian: crowded long = bearish
    z_spread = expanding_zscore(panel["wti_brent_spread"])   # WTI strengthening vs Brent = bullish WTI

    panel["z_inventory"] = z_inv
    panel["z_production"] = z_prod
    panel["z_positioning_contrarian"] = z_pos
    panel["z_wti_brent"] = z_spread
    panel["composite"] = panel[
        ["z_inventory", "z_production", "z_positioning_contrarian", "z_wti_brent"]
    ].mean(axis=1)

    panel = panel.dropna()
    return panel


def evaluate_explanatory_power(panel):
    fwd_ret = panel["wti_price"].shift(-FORWARD_WINDOW // 5) / panel["wti_price"] - 1
    # weekly data -> FORWARD_WINDOW is in trading days; ~4 trading weeks = 4 weekly obs
    data = pd.DataFrame({"composite": panel["composite"], "fwd_ret": fwd_ret}).dropna()

    n = len(data)
    split = int(n * TRAIN_FRAC)
    train, test = data.iloc[:split], data.iloc[split:]

    def fit_report(d, label):
        x = d["composite"].values
        y = d["fwd_ret"].values
        beta, alpha = np.polyfit(x, y, 1)
        pred = alpha + beta * x
        resid = y - pred
        ss_res = (resid**2).sum()
        ss_tot = ((y - y.mean())**2).sum()
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
        corr = np.corrcoef(x, y)[0, 1]
        hit_rate = (np.sign(x) == np.sign(y)).mean()
        return {"label": label, "n": len(d), "beta": beta, "corr": corr, "r2": r2, "hit_rate": hit_rate}

    return fit_report(train, "train"), fit_report(test, "test")


def main():
    panel = build_indicators()
    train_stats, test_stats = evaluate_explanatory_power(panel)

    stats_df = pd.DataFrame([train_stats, test_stats]).set_index("label")
    print(stats_df.to_string(float_format=lambda x: f"{x:.4f}"))
    stats_df.to_csv("explanatory_power.csv")

    panel.to_csv("panel_full.csv")

    latest = panel.iloc[-1]
    print("\nLatest readings:")
    print(latest[["inv_dev", "prod_yoy", "net_mm_pct_oi", "wti_brent_spread",
                   "z_inventory", "z_production", "z_positioning_contrarian",
                   "z_wti_brent", "composite"]])

    return panel, stats_df


if __name__ == "__main__":
    main()
