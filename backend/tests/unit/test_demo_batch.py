from app.simulation.demo_batch import assert_covers_all_diagnoses


def test_curated_demo_batch_covers_all_six_diagnoses():
    """Plan.md §6.1 Edit 3, 'Done when': the curated batch contains at least
    one invoice of every diagnosis code, so the video never has to hunt for
    one. Runs the real generator + real cascade, not a mock.
    """
    assert_covers_all_diagnoses()
