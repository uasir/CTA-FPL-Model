import copy
import json
from pathlib import Path

from compare_fpl_personal_squad_outputs import compare
from personal_squad_engine import recommend_personal_squad


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "recommendation_requests.json").read_text(encoding="utf-8")
)


def test_personal_squad_parity_comparator_accepts_identical_engine_outputs():
    request = copy.deepcopy(FIXTURE["personal_squad"])
    python_result = recommend_personal_squad(request)
    report = compare(python_result, python_result)
    assert report["status"] == "PASS_PERSONAL_SQUAD_PYTHON_JAVASCRIPT_PARITY"
    assert report["starting_xi_count"] == 11


def test_personal_squad_parity_comparator_reports_first_divergence():
    request = copy.deepcopy(FIXTURE["personal_squad"])
    python_result = recommend_personal_squad(request)
    javascript_result = copy.deepcopy(python_result)
    javascript_result["transfer_recommendation"]["candidate_count"] += 1
    report = compare(python_result, javascript_result)
    assert report["status"] == "FAIL_PERSONAL_SQUAD_PYTHON_JAVASCRIPT_PARITY"
    assert report["first_difference"]["path"] == "$.transfer_recommendation.candidate_count"
