"""Generate scorecard_vs_price.png from panel_full.csv (produced by oil_scorecard.py)."""
import pandas as pd
import matplotlib.pyplot as plt

panel = pd.read_csv("panel_full.csv", index_col=0, parse_dates=True)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 6.5), sharex=True,
                                gridspec_kw={"height_ratios": [2, 1.3]})

ax1.plot(panel.index, panel["wti_price"], color="#1f77b4", linewidth=1.2)
ax1.set_title("WTI price vs supply/demand composite score")
ax1.set_ylabel("WTI price (USD/bbl)")
ax1.grid(alpha=0.25)

ax2.plot(panel.index, panel["composite"], color="#d62728", linewidth=1.1)
ax2.axhline(0, color="grey", linewidth=0.8, linestyle="--")
ax2.set_ylabel("Composite z-score\n(+ = bullish signal)")
ax2.grid(alpha=0.25)

fig.autofmt_xdate()
fig.tight_layout()
fig.savefig("scorecard_vs_price.png", dpi=150)
print("saved scorecard_vs_price.png")
