SELECT 'CREATE ROLE grafana_reader LOGIN'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_roles
    WHERE rolname = 'grafana_reader'
)
\gexec

SELECT format(
    'ALTER ROLE grafana_reader PASSWORD %L',
    :'grafana_password'
)
\gexec

GRANT CONNECT ON DATABASE :"db_name" TO grafana_reader;
GRANT USAGE ON SCHEMA public TO grafana_reader;
GRANT SELECT ON TABLE
    public.inference_jobs,
    public.inference_job_stages
TO grafana_reader;
