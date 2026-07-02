import os
import pandas as pd
import matplotlib.pyplot as plt

# =================================
# CREATE OUTPUT FOLDER
# =================================

os.makedirs(
    "charts",
    exist_ok=True
)

# =================================
# LOAD DATASET
# =================================

df = pd.read_csv(
    "data/smart_logistics_dataset.csv"
)

print(
    f"Total Orders: {len(df)}"
)

# =================================
# STATUS COUNT
# =================================

status_count = (
    df["delivery_status"]
    .value_counts()
)

print("\nOrder Status Summary:")
print(status_count)

# =================================
# PLOT
# =================================

plt.figure(
    figsize=(10, 6)
)

ax = status_count.plot(
    kind="bar"
)

# =================================
# VALUE LABELS
# =================================

for i, value in enumerate(status_count):

    ax.text(
        i,
        value + 5,
        str(value),
        ha="center"
    )

# =================================
# STYLE
# =================================

plt.title(
    f"Order Status Distribution ({len(df)} Orders)"
)

plt.xlabel(
    "Order Status"
)

plt.ylabel(
    "Number of Orders"
)

plt.grid(
    axis="y",
    alpha=0.3
)

plt.tight_layout()

# =================================
# SAVE
# =================================

output_file = (
    "charts/order_status_distribution.png"
)

plt.savefig(
    output_file,
    dpi=300
)

print(
    f"\nChart saved to: {output_file}"
)

plt.show()