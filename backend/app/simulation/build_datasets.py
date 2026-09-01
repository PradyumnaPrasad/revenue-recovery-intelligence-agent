"""One command regenerates every dataset from seeds — plan.md §6.4 "done
when". Run as `python -m app.simulation.build_datasets`.

Writes JSONL under data/:
  data/train.jsonl        — TRAIN_SEEDS x E_train      (model training)
  data/calibration.jsonl  — CALIBRATION_SEEDS x E_train (isotonic calibration, M2)
  data/eval_{env}.jsonl   — EVALUATION_SEEDS x each of the 3 environments
                            (robustness reporting, M7)

Every file is fully reproducible: delete data/, rerun this module, and the
byte content is identical (same seeds -> same generator output -> same
sampled actions/outcomes, since every RNG here is seeded, never wall-clock
or os.urandom).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.simulation.environment import ENVIRONMENTS
from app.simulation.training_data import (
    CALIBRATION_SEEDS,
    EVALUATION_SEEDS,
    TRAIN_SEEDS,
    assert_no_leakage,
    generate_labeled_dataset,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SIZE_PER_SEED = 300


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(asdict(row), default=str) + "\n")


def main() -> None:
    train_rows = generate_labeled_dataset(
        TRAIN_SEEDS, SIZE_PER_SEED, ENVIRONMENTS["E_train"], fold="train"
    )
    assert_no_leakage(train_rows)
    _write_jsonl(DATA_DIR / "train.jsonl", train_rows)
    print(f"train.jsonl: {len(train_rows)} rows from seeds {TRAIN_SEEDS}")

    calib_rows = generate_labeled_dataset(
        CALIBRATION_SEEDS, SIZE_PER_SEED, ENVIRONMENTS["E_train"], fold="calibration"
    )
    assert_no_leakage(calib_rows)
    _write_jsonl(DATA_DIR / "calibration.jsonl", calib_rows)
    print(f"calibration.jsonl: {len(calib_rows)} rows from seeds {CALIBRATION_SEEDS}")

    for env_name, env in ENVIRONMENTS.items():
        eval_rows = generate_labeled_dataset(
            EVALUATION_SEEDS, SIZE_PER_SEED, env, fold="evaluation"
        )
        assert_no_leakage(eval_rows)
        out = DATA_DIR / f"eval_{env_name}.jsonl"
        _write_jsonl(out, eval_rows)
        print(f"{out.name}: {len(eval_rows)} rows from seeds {EVALUATION_SEEDS}")


if __name__ == "__main__":
    main()
