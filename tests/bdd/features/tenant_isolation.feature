Feature: Tenant isolation
  PLAN §2 "Auth": Postgres RLS on tenant_id, driven only by the validated
  JWT's `tenant` claim, never client input (CLAUDE.md "tenant/role always
  comes from the JWT server-side"). tests/integration/test_postgres_rls.py
  already proves this at the database layer directly; this proves it through
  the real, running API — a genuine cross-tenant alert must never appear in
  a demo-tenant user's own results.

  Scenario: An alert belonging to another tenant never appears in this tenant's list
    Given a rogue alert planted for a brand-new second tenant
    When "fleet_manager" lists open alerts
    Then none of the returned alerts belong to the rogue tenant
