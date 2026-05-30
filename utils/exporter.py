import os
import json
import pandas as pd

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def save_csv(records, output_path: str):
    ensure_dir(os.path.dirname(output_path))
    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False)

def save_json(records, output_path: str):
    ensure_dir(os.path.dirname(output_path))
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
