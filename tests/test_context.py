import context


def test_fetch_beds_returns_hospitals():
    beds = context.fetch_beds()
    assert isinstance(beds, list)
    assert len(beds) >= 1
    # Real feed keys (verified against the live API).
    assert "health_facility_name" in beds[0]
    assert "district_name" in beds[0]
    assert "free_beds" in beds[0]


def test_fetch_beds_empty_when_down(monkeypatch):
    def _raise(*a, **k):
        raise Exception("offline")
    monkeypatch.setattr(context.requests, "get", _raise)
    assert context.fetch_beds() == []

