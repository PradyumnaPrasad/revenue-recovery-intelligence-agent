"""Structural enforcement of plan.md §6.4 Change 4 (oracle hygiene): the
model must never see anything beyond invoice facts + diagnosis + action.
"""
from app.domain.features import ALLOWED_FEATURE_KEYS, FeatureVector, to_feature_vector
from app.domain.types import ActionKey, DiagnosisCode, InvoiceFacts


def _facts() -> InvoiceFacts:
    return InvoiceFacts(
        invoice_id="inv-1",
        amount_paise=250_000_00,
        days_overdue=45,
        dispute_flag=False,
        prior_late_payment_rate=0.48,
        prior_broken_promises=1,
        prior_invoice_count=12,
        contact_count_30d=2,
        payment_link_sent=True,
        payment_link_opened=False,
    )


def test_feature_vector_schema_matches_allowlist_exactly():
    assert set(FeatureVector.model_fields.keys()) == ALLOWED_FEATURE_KEYS


def test_to_feature_vector_leaks_nothing_extra():
    fv = to_feature_vector(
        facts=_facts(),
        diagnosis_code=DiagnosisCode.cash_flow_risk,
        action=ActionKey.offer_payment_plan,
        segment="mid_market",
        industry="manufacturing",
    )
    assert set(fv.model_dump().keys()) == ALLOWED_FEATURE_KEYS


def test_no_environment_symbol_in_feature_vector_source():
    """Belt-and-suspenders: app/domain/features.py must not IMPORT the
    simulation environment module — the allowlist should be enforced by the
    function signature not being able to accept environment state, not just
    by discipline. (Checks for an actual import, not the word "environment"
    in a comment — the module's own docstring explains this guarantee in
    prose, which would otherwise false-positive.)
    """
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[2] / "app" / "domain" / "features.py").read_text()
    tree = ast.parse(src)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

    assert not any("environment" in m for m in imported_modules), imported_modules
    assert not any("simulation" in m for m in imported_modules), imported_modules
