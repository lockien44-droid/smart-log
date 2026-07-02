import os
import pandas as pd
import matplotlib.pyplot as plt

# =================================
# CREATE CHART FOLDER
# =================================

os.makedirs("charts", exist_ok=True)

# =================================
# LOAD DATA
# =================================

df = pd.read_csv(
    "data/smart_logistics_dataset.csv"
)

# =================================
# INVENTORY DISTRIBUTION
# =================================

plt.figure(
    figsize=(10, 6)
)

plt.hist(
    df["inventory_quantity"],
    bins=20,
    edgecolor="black"
)

plt.axvline(
    df["inventory_quantity"].mean(),
    linestyle="--",
    label=f"Mean = {df['inventory_quantity'].mean():.0f}"
)

plt.title(
    "Inventory Quantity Distribution"
)

plt.xlabel(
    "Inventory Quantity"
)

plt.ylabel(
    "Frequency"
)

plt.legend()

plt.grid(
    alpha=0.3
)

plt.tight_layout()

# =================================
# SAVE
# =================================

chart_path = (
    "charts/inventory_distribution.png"
)

plt.savefig(
    chart_path,
    dpi=300
)

print(
    f"Chart saved: {chart_path}"
)

plt.show()