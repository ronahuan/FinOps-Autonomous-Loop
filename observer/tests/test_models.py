"""Tests for models and costmgmt fixture loading."""
from pathlib import Path

from observer.models import Intent, Recommendation, ResourceSet
from observer.costmgmt import load_fixture, _parse

FIXTURE = Path(__file__).parent / "fixtures" / "recommendation.json"


class TestResourceSet:
    def test_round_trip(self):
        rs = ResourceSet(cpu_request="500m", memory_request="512Mi")
        assert rs.cpu_request == "500m"
        assert rs.memory_request == "512Mi"


class TestRecommendation:
    def test_from_fixture_dict(self):
        raw = {
            "cluster": "crc",
            "namespace": "finops-demo",
            "workload": "waster",
            "workload_type": "Deployment",
            "container": "waster",
            "current": {"cpu_request": "500m", "memory_request": "512Mi"},
            "recommended": {"cpu_request": "50m", "memory_request": "64Mi"},
            "recommendation_term": "15d",
            "last_reported": "2026-06-01T00:00:00Z",
        }
        rec = _parse(raw)
        assert rec.workload == "waster"
        assert rec.current.cpu_request == "500m"
        assert rec.recommended.memory_request == "64Mi"


class TestIntent:
    def test_defaults(self):
        intent = Intent(
            cluster="crc",
            namespace="finops-demo",
            workload="waster",
            workload_type="Deployment",
            container="waster",
            current=ResourceSet(cpu_request="500m", memory_request="512Mi"),
            recommended=ResourceSet(cpu_request="50m", memory_request="64Mi"),
            recommendation_term="15d",
            last_reported="2026-06-01T00:00:00Z",
        )
        assert intent.stage == "proposed"
        assert intent.decision == "block"
        assert intent.reasons == []
        assert intent.monthly_saving_estimate == 0.0

    def test_intent_inherits_recommendation(self):
        assert issubclass(Intent, Recommendation)

    def test_schema_has_required_fields(self):
        schema = Intent.model_json_schema()
        assert "cluster" in schema["required"]
        assert "current" in schema["required"]
        assert "stage" not in schema["required"]


class TestLoadFixture:
    def test_loads_fixture_file(self):
        recs = load_fixture(FIXTURE)
        assert len(recs) == 1
        assert recs[0].workload == "waster"
        assert recs[0].current.cpu_request == "500m"
        assert recs[0].recommended.cpu_request == "50m"

    def test_fixture_has_no_intent_fields(self):
        import json
        data = json.loads(FIXTURE.read_text())
        for item in data:
            assert "stage" not in item
            assert "decision" not in item
            assert "monthly_saving_estimate" not in item
