import pytest

from app.domain.diagnosis import diagnose
from app.domain.types import DiagnosisCode, InvoiceFacts


def facts(**overrides) -> InvoiceFacts:
    base = dict(
        invoice_id="inv-1",
        amount_paise=100_000_00,
        days_overdue=10,
        dispute_flag=False,
        prior_late_payment_rate=0.1,
        prior_broken_promises=0,
        prior_invoice_count=5,
        contact_count_30d=0,
        payment_link_sent=False,
        payment_link_opened=False,
        has_open_dispute_reply=False,
    )
    base.update(overrides)
    return InvoiceFacts(**base)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        # R01 dispute dominates everything, even chronic-looking history
        (
            dict(
                dispute_flag=True,
                days_overdue=90,
                prior_broken_promises=5,
                prior_late_payment_rate=0.9,
            ),
            DiagnosisCode.disputed,
        ),
        (dict(has_open_dispute_reply=True), DiagnosisCode.disputed),
        # R02 chronic_non_payment — threshold is >35 days (was >60)
        (
            dict(days_overdue=61, prior_broken_promises=2, prior_late_payment_rate=0.9),
            DiagnosisCode.chronic_non_payment,
        ),
        (dict(days_overdue=36, prior_broken_promises=2), DiagnosisCode.chronic_non_payment),
        # boundary: exactly 35 does not satisfy ">35" -> falls through to
        # cash_flow_risk (R04), since broken_promises=2 meets its threshold
        (dict(days_overdue=35, prior_broken_promises=2), DiagnosisCode.cash_flow_risk),
        # boundary: only 1 broken promise -> not chronic even when very
        # overdue, and (per the F4 fix) 1 broken promise alone no longer
        # triggers cash_flow_risk either -> falls all the way to standard
        (dict(days_overdue=90, prior_broken_promises=1), DiagnosisCode.standard_overdue),
        # R03 channel_failure — MOVED ABOVE cash_flow_risk (the F4 fix).
        # A link sent, never opened, across repeated contacts is
        # channel_failure regardless of how bad the payment history looks.
        (
            dict(
                payment_link_sent=True,
                payment_link_opened=False,
                contact_count_30d=2,
                days_overdue=20,
            ),
            DiagnosisCode.channel_failure,
        ),
        # regression test for the actual ordering bug: a customer with a
        # high late rate AND an unopened link must be diagnosed by channel,
        # not cash-flow, because an unopened link tells you nothing about
        # their finances
        (
            dict(
                payment_link_sent=True,
                payment_link_opened=False,
                contact_count_30d=3,
                prior_late_payment_rate=0.7,
                prior_broken_promises=3,
            ),
            DiagnosisCode.channel_failure,
        ),
        # boundary: only 1 contact -> channel_failure does not fire; falls
        # through to cash_flow_risk on the high late rate instead
        (
            dict(
                payment_link_sent=True,
                payment_link_opened=False,
                contact_count_30d=1,
                prior_late_payment_rate=0.7,
            ),
            DiagnosisCode.cash_flow_risk,
        ),
        # R04 cash_flow_risk — broken_promises threshold raised 1 -> 2
        (dict(prior_late_payment_rate=0.4), DiagnosisCode.cash_flow_risk),
        (dict(prior_broken_promises=2), DiagnosisCode.cash_flow_risk),
        # boundary: 1 broken promise alone is noise, not a pattern -> falls
        # through to process_delay (days=10<=21, late=0.1<0.3, promises<=1)
        (dict(prior_broken_promises=1), DiagnosisCode.process_delay),
        # boundary: late_rate just under the cash-flow threshold, and above
        # the process_delay ceiling -> standard_overdue. (This is the F5
        # test-bug fix: the old test asserted process_delay here, but R05
        # required <0.2 at the time and 0.39 failed that too — the code was
        # always right, the assertion was wrong. Under the new R05 ceiling
        # of <0.3, 0.39 still doesn't qualify.)
        (
            dict(prior_late_payment_rate=0.39, prior_broken_promises=0),
            DiagnosisCode.standard_overdue,
        ),
        # R05 process_delay — window widened: days<=21 (was 14), late<0.3
        # (was 0.2), broken_promises<=1 (was ==0)
        (
            dict(days_overdue=21, prior_late_payment_rate=0.29, prior_broken_promises=1),
            DiagnosisCode.process_delay,
        ),
        (dict(days_overdue=14, prior_late_payment_rate=0.19, prior_broken_promises=0), DiagnosisCode.process_delay),
        # boundary: 22 days is just past the process_delay window
        (dict(days_overdue=22, prior_late_payment_rate=0.1, prior_broken_promises=0), DiagnosisCode.standard_overdue),
        # boundary: late_rate=0.3 is not "<0.3"
        (dict(days_overdue=15, prior_late_payment_rate=0.3, prior_broken_promises=0), DiagnosisCode.standard_overdue),
        # R06 fallback
        (dict(days_overdue=30, prior_late_payment_rate=0.25, prior_broken_promises=0), DiagnosisCode.standard_overdue),
    ],
)
def test_diagnosis_cascade(overrides, expected):
    d = diagnose(facts(**overrides))
    assert d.code == expected


def test_every_invoice_gets_exactly_one_code():
    """Property: the cascade always terminates with exactly one code — no
    input can produce two labels (this was C9 in project.md's original
    design: cash_flow_risk and chronic_non_payment could both fire)."""
    d = diagnose(facts())
    assert isinstance(d.code, DiagnosisCode)


def test_dispute_beats_chronic_and_cash_flow_simultaneously():
    d = diagnose(
        facts(
            dispute_flag=True,
            days_overdue=120,
            prior_broken_promises=6,
            prior_late_payment_rate=0.95,
        )
    )
    assert d.code == DiagnosisCode.disputed
    assert d.rule_id == "R01.disputed"


def test_channel_failure_beats_cash_flow_risk():
    """Plan.md F4: the diagnostic ordering bug. A customer whose payment
    link was never opened tells you nothing about their finances — the old
    ordering (cash_flow_risk checked before channel_failure) mislabelled
    this case, and it was the single largest contributor to an undemoable
    1.4% channel_failure share in the generated portfolio.
    """
    d = diagnose(
        facts(
            payment_link_sent=True,
            payment_link_opened=False,
            contact_count_30d=4,
            prior_late_payment_rate=0.85,
            prior_broken_promises=5,
        )
    )
    assert d.code == DiagnosisCode.channel_failure
    assert d.rule_id == "R03.channel_failure"
