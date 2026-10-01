#!/bin/sh
set -eu
psql --username postgres --dbname forvalta --set=app_password="$APP_DB_PASSWORD" --set=ON_ERROR_STOP=1 <<'SQL'
SELECT format('CREATE ROLE forvalta LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'app_password') \gexec
GRANT CONNECT ON DATABASE forvalta TO forvalta;
ALTER SCHEMA public OWNER TO forvalta;
SQL
