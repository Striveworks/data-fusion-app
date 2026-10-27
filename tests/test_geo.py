from app.geo import haversine_meters


def test_haversine_same_point_is_zero():
    assert haversine_meters(21.3, -157.8, 21.3, -157.8) == 0


def test_haversine_known_distance():
    # About 111.2 km per degree of latitude.
    meters = haversine_meters(0, 0, 1, 0)
    assert 110_000 < meters < 112_000
