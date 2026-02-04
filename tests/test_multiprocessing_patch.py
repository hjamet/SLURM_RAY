"""
Test for the ray.util.multiprocessing patch in SlurmRay.

This test verifies that the multiprocessing patch works correctly,
allowing code that uses multiprocessing.Pool to run within SlurmRay.
"""

import pytest
from slurmray import Cluster


def mp_pool_task():
    """Task that uses multiprocessing.Pool - this would fail without the Ray patch."""
    from multiprocessing import Pool
    
    def square(x):
        return x * x
    
    with Pool(2) as p:
        results = p.map(square, [1, 2, 3, 4, 5])
    
    return results


def test_multiprocessing_patch_local():
    """Verify that multiprocessing.Pool works via Ray patch in local mode."""
    launcher = Cluster(
        project_name="test_mp_patch",
        cluster="local",
        num_cpus=2,
        num_gpus=0,
        max_running_time=5
    )
    
    result = launcher(mp_pool_task)
    assert result == [1, 4, 9, 16, 25], f"Expected [1, 4, 9, 16, 25], got {result}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
