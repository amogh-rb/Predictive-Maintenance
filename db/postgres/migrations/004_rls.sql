-- Tenant isolation (PLAN §2 "Auth" / §2 "Data stores" CP row). The API
-- (session 6) runs `SET LOCAL app.tenant_id = '<uuid>'` per request from the
-- validated JWT before touching any of these tables; nothing here trusts a
-- client-supplied tenant column. FORCE ROW LEVEL SECURITY so even the table
-- owner (the app's DB role) is bound by the policy, not just other roles.
-- vehicle_model, dtc_kb and failure_signature are shared catalogues with no
-- tenant_id and are intentionally left out.

DO $$
DECLARE
    t text;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'depot', 'driver', 'vehicle', 'app_user', 'subscription',
        'alert', 'work_order', 'prediction', 'audit_log'
    ])
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I '
            'USING (tenant_id = current_setting(''app.tenant_id'', true)::uuid) '
            'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true)::uuid)',
            t
        );
    END LOOP;
END $$;
