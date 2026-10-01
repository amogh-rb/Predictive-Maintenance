"""Step defs shared by more than one feature file — kept in one place so
behave never registers the same pattern twice (an ambiguous-step error).
"""
from __future__ import annotations

from behave import then


@then("the request is rejected with status {code:d}")
def step_rejected_with_status(context, code):
    assert context.response.status_code == code, context.response.text
