"""Worker-slice contracts for credential-free GPU input packaging."""

import pytest

from scripts.package_gpu_inputs import partition_dates


def test_four_worker_partition_is_exact_balanced_and_ordered() -> None:
    dates = [f"date-{index:02d}" for index in range(56)]
    slices = partition_dates(dates, 4)

    assert [len(part) for part in slices] == [14, 14, 14, 14]
    assert [date for part in slices for date in part] == dates
    assert len({date for part in slices for date in part}) == 56


def test_partition_balances_remainder_without_duplication() -> None:
    dates = ["a", "b", "c", "d", "e"]
    assert partition_dates(dates, 2) == [["a", "b", "c"], ["d", "e"]]


@pytest.mark.parametrize("workers", [0, 4])
def test_partition_rejects_impossible_worker_counts(workers: int) -> None:
    with pytest.raises(ValueError):
        partition_dates(["a", "b", "c"], workers)
