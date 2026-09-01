"""One dict, no pipeline changes to add a source — plan.md §6.0 'Done
when': "a second source can be registered in <20 lines with no pipeline
edits." CheckoutAbandonmentSource is that proof: it cost 30 lines total
(app/sources/checkout_abandonment.py) and one line here.
"""
from __future__ import annotations

from app.sources.base import RiskSource
from app.sources.checkout_abandonment import CheckoutAbandonmentSource
from app.sources.receivables import ReceivablesSource

RISK_SOURCES: dict[str, RiskSource] = {
    "receivables": ReceivablesSource(),
    "checkout_abandonment": CheckoutAbandonmentSource(),
}
