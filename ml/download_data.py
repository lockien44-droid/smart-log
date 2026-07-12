from pathlib import Path
import shutil
import tempfile

import kagglehub


DATASET_HANDLE = (
    "atomicd/"
    "retail-store-inventory-and-demand-forecasting"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
RAW_SOURCE_FILE = RAW_DATA_DIR / "demand_forecasting.csv"


def download_dataset():
    """Download the Kaggle CSV into the single canonical raw-data path."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("[KAGGLE] Downloading dataset...")
    with tempfile.TemporaryDirectory(prefix="kaggle_demand_") as temp_dir:
        download_dir = Path(temp_dir)
        path = kagglehub.dataset_download(
            DATASET_HANDLE,
            output_dir=str(download_dir),
        )

        csv_files = sorted(download_dir.rglob("*.csv"))
        if not csv_files:
            raise FileNotFoundError(
                "Kaggle download completed but no CSV file was found."
            )

        preferred_names = [
            "demand_forecasting.csv",
            "train.csv",
        ]
        source_csv = next(
            (
                candidate
                for name in preferred_names
                for candidate in csv_files
                if candidate.name.lower() == name
            ),
            csv_files[0],
        )
        shutil.copyfile(source_csv, RAW_SOURCE_FILE)

        print(f"[KAGGLE] Download directory: {path}")
        print(f"[KAGGLE] Canonical raw file: {RAW_SOURCE_FILE}")
        print(f"[KAGGLE] Selected CSV: {source_csv}")

    return [RAW_SOURCE_FILE]


if __name__ == "__main__":
    download_dataset()
