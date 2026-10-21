-- Bootstrap only; no personal records or production data release is created.
\set ON_ERROR_STOP on
\getenv app_password SAZU_DB_PASSWORD
CREATE ROLE sazu_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
REVOKE ALL ON DATABASE sazu FROM PUBLIC;
GRANT CONNECT ON DATABASE sazu TO sazu_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
