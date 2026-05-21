import pytest
import numpy as np
from app.pipeline import (
    compute_euclidean_distance,
    distance_point_to_box,
    smooth_states,
    segment_intervals,
)

def test_compute_euclidean_distance():
    # Test simple pairs
    assert compute_euclidean_distance((0, 0), (3, 4)) == 5.0
    assert compute_euclidean_distance((10, 10), (10, 10)) == 0.0
    assert pytest.approx(compute_euclidean_distance((1, 2), (4, 6))) == 5.0

def test_distance_point_to_box():
    box = [10, 10, 20, 20] # xmin, ymin, xmax, ymax
    
    # 1. Point inside the box (should be 0.0)
    assert distance_point_to_box(15, 15, box) == 0.0
    assert distance_point_to_box(10, 10, box) == 0.0 # Boundary edge
    
    # 2. Point directly above the box
    assert distance_point_to_box(15, 5, box) == 5.0
    
    # 3. Point directly to the left of the box
    assert distance_point_to_box(5, 15, box) == 5.0
    
    # 4. Point diagonally from top-left corner
    # Top-left is (10, 10). Test point is (7, 6).
    # dx = 3, dy = 4, distance should be 5
    assert distance_point_to_box(7, 6, box) == 5.0

def test_smooth_states():
    # 1. Window of all stationary
    states = [0, 0, 0, 0, 0]
    assert smooth_states(states, window_size=3) == [0, 0, 0, 0, 0]
    
    # 2. Singular flicker should be smoothed out
    # Majority of 3 elements centered around index 2 is: sub[1:4] = [0, 1, 0] -> majority 0
    flicker = [0, 0, 1, 0, 0]
    assert smooth_states(flicker, window_size=3) == [0, 0, 0, 0, 0]
    
    # 3. Sustained state should be preserved
    sustained = [0, 0, 1, 1, 1, 1, 0]
    # Indices 2, 3, 4, 5 should remain 1 under size 3
    assert smooth_states(sustained, window_size=3) == [0, 0, 1, 1, 1, 1, 0]

def test_segment_intervals():
    frames = [10, 11, 12, 13, 14, 15]
    
    # 1. Monolithic state
    all_stationary = [0, 0, 0, 0, 0, 0]
    res1 = segment_intervals(frames, all_stationary)
    assert len(res1) == 1
    assert res1[0]["frame_range"] == [10, 15]
    assert res1[0]["state"] == "stationary"
    
    # 2. Transition state
    transition = [0, 0, 0, 1, 1, 1]
    res2 = segment_intervals(frames, transition)
    assert len(res2) == 2
    assert res2[0]["frame_range"] == [10, 12]
    assert res2[0]["state"] == "stationary"
    assert res2[1]["frame_range"] == [13, 15]
    assert res2[1]["state"] == "moving"
    
    # 3. Fluctuation (e.g. stationary -> moving -> stationary)
    fluctuate = [0, 0, 1, 1, 0, 0]
    res3 = segment_intervals(frames, fluctuate)
    assert len(res3) == 3
    assert res3[0]["frame_range"] == [10, 11]
    assert res3[0]["state"] == "stationary"
    assert res3[1]["frame_range"] == [12, 13]
    assert res3[1]["state"] == "moving"
    assert res3[2]["frame_range"] == [14, 15]
    assert res3[2]["state"] == "stationary"
