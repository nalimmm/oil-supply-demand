"""
Download all raw data needed by oil_scorecard.py, from scratch.

Sources (all public, no API key required):
  - CFTC Disaggregated Commitments of Traders, bulk annual history files
    (https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed)
  - EIA weekly petroleum data, direct .xls downloads
    (https://www.eia.gov/petroleum/data.php)

Note: the CFTC contract code for WTI crude oil futures is 067651. The
market name attached to that code changed from "CRUDE OIL, LIGHT SWEET"
to "WTI-PHYSICAL" partway through 2022 - this script filters by CODE,
not by name, to get an unbroken history across that renaming.
"""

import os
import zipfile
import io
import urllib.request

import pandas as pd

RAW_DIR = "rawdata"
CFTC_CODE_WTI = "067651"
YEARS = range(2015, 2027)

EIA_STOCKS_URL = "https://www.eia.gov/dnav/pet/hist_xls/WCESTUS1w.xls"
EIA_PRODUCTION_URL = "https://www.eia.gov/dnav/pet/hist_xls/WCRFPUS2w.xls"


HEADERS = {"User-Agent": "Mozilla/5.0 (research script; contact: n/a)"}


def _download(url, path):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp, open(path, "wb") as f:
        f.write(resp.read())


def _get_bytes(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def fetch_cftc():
    os.makedirs(RAW_DIR, exist_ok=True)
    frames = []
    cols_needed = [
        "Market_and_Exchange_Names", "Report_Date_as_YYYY-MM-DD",
        "CFTC_Contract_Market_Code", "Open_Interest_All",
        "M_Money_Positions_Long_All", "M_Money_Positions_Short_All",
    ]
    for year in YEARS:
        url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
        try:
            data = _get_bytes(url)
        except Exception as e:
            print(f"skip {year}: {e}")
            continue
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = z.namelist()[0]
            with z.open(name) as f:
                df = pd.read_csv(f, low_memory=False, usecols=lambda c: c in cols_needed)
        sub = df[df["CFTC_Contract_Market_Code"].astype(str).str.strip() == CFTC_CODE_WTI].copy()
        frames.append(sub)

    full = pd.concat(frames, ignore_index=True)
    full["Report_Date_as_YYYY-MM-DD"] = pd.to_datetime(full["Report_Date_as_YYYY-MM-DD"])
    full = full.sort_values("Report_Date_as_YYYY-MM-DD").drop_duplicates("Report_Date_as_YYYY-MM-DD")
    full["net_mm"] = full["M_Money_Positions_Long_All"] - full["M_Money_Positions_Short_All"]
    full["net_mm_pct_oi"] = full["net_mm"] / full["Open_Interest_All"]
    out_path = os.path.join(RAW_DIR, "cftc_wti_clean.csv")
    full.to_csv(out_path, index=False)
    print(f"saved {out_path} ({len(full)} weekly rows, "
          f"{full['Report_Date_as_YYYY-MM-DD'].min().date()} to "
          f"{full['Report_Date_as_YYYY-MM-DD'].max().date()})")


def fetch_eia():
    os.makedirs(RAW_DIR, exist_ok=True)
    _download(EIA_STOCKS_URL, os.path.join(RAW_DIR, "wti_stocks.xls"))
    _download(EIA_PRODUCTION_URL, os.path.join(RAW_DIR, "wti_production.xls"))
    print("saved rawdata/wti_stocks.xls and rawdata/wti_production.xls")


if __name__ == "__main__":
    fetch_cftc()
    fetch_eia()
