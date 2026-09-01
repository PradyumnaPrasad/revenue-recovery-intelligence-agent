from app.simulation.environment import ENVIRONMENTS
from app.simulation.training_data import (
    CALIBRATION_SEEDS,
    EVALUATION_SEEDS,
    TRAIN_SEEDS,
    assert_no_leakage,
    generate_labeled_dataset,
)


def test_fold_seeds_are_disjoint():
    train = set(TRAIN_SEEDS)
    calib = set(CALIBRATION_SEEDS)
    ev = set(EVALUATION_SEEDS)
    assert train.isdisjoint(calib)
    assert train.isdisjoint(ev)
    assert calib.isdisjoint(ev)


def test_dataset_is_reproducible():
    rows1 = generate_labeled_dataset(TRAIN_SEEDS[:1], 100, ENVIRONMENTS["E_train"], fold="train")
    rows2 = generate_labeled_dataset(TRAIN_SEEDS[:1], 100, ENVIRONMENTS["E_train"], fold="train")
    assert [(r.features, r.recovered) for r in rows1] == [(r.features, r.recovered) for r in rows2]


def test_no_leakage_across_all_three_environments():
    for env in ENVIRONMENTS.values():
        rows = generate_labeled_dataset(EVALUATION_SEEDS[:1], 100, env, fold="evaluation")
        assert_no_leakage(rows)  # raises on violation


def test_every_row_has_a_binary_outcome():
    rows = generate_labeled_dataset(TRAIN_SEEDS[:1], 50, ENVIRONMENTS["E_train"], fold="train")
    assert all(isinstance(r.recovered, bool) for r in rows)
    assert 0.0 < sum(r.recovered for r in rows) / len(rows) < 1.0  # not degenerate
