from pathlib import Path

import kagglehub


DATASET_HANDLE = (
    "talhanazir168/"
    "store-inventory-demand-forecasting-dataset"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "kaggle_demand"


def download_dataset():
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("[KAGGLE] Downloading dataset...")
    path = kagglehub.dataset_download(
        DATASET_HANDLE,
        output_dir=str(RAW_DATA_DIR),
    )

    csv_files = sorted(RAW_DATA_DIR.rglob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            "Kaggle download completed but no CSV file was found."
        )

    print(f"[KAGGLE] Download directory: {path}")
    for csv_file in csv_files:
        print(f"[KAGGLE] CSV: {csv_file}")

    return csv_files


if __name__ == "__main__":
    download_dataset()
