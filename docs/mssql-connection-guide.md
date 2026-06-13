# MSSQL Connection Guide

How the platform connects to a user-provided Microsoft SQL Server (SAP B1),
what was fixed to make it work, and how to verify a connection.

## Connection path (code map)

| Step | File | What happens |
|---|---|---|
| 1. Create | `backend/app/api/v1/endpoints/connections.py` → `POST /api/v1/connections` | Validates payload (`schemas/connection.py`), requires platform_admin |
| 2. Store | `backend/app/services/connections/connection_service.py` | Credentials serialized with `json.dumps`, AES-256-GCM encrypted (`core/encryption.py`), stored in `connections.vault_credential_path` as `local:{blob}`. Password is double-encrypted (per-field + whole blob) and never returned by any API |
| 3. Test | `POST /api/v1/connections/{id}/test` → `MSSQLConnector` in `services/connections/connector.py` | pyodbc connect, `SELECT @@VERSION`, read-only probe, latency. Failures feed the Redis circuit breaker (`circuit_breaker.py`) |
| 4. Discover | `POST /api/v1/discovery/{id}/start` → Celery task `worker/tasks/discovery.py` | Worker decrypts credentials, opens its own pyodbc connection, crawls `INFORMATION_SCHEMA` into `metadata_*` tables |

All MSSQL connection strings are built by **one** shared helper:
`build_mssql_conn_str()` in `backend/app/services/connections/connector.py`.

## Connection string semantics

```
DRIVER={ODBC Driver 18 for SQL Server};SERVER=<host>,<port>;DATABASE=<db>;
UID=<user>;PWD={<escaped>};Encrypt=<yes|no>;TrustServerCertificate=yes;
```

- `Encrypt` follows the connection's `is_tls` flag (UI checkbox / API field).
- `TrustServerCertificate=yes` always: SAP B1 on-prem servers almost always
  run self-signed certificates; traffic is still encrypted when `Encrypt=yes`,
  the certificate chain just isn't validated.
- The password is brace-wrapped with `}` doubled, so passwords containing
  `;`, `=`, `{`, `}` cannot break the string.
- Note: SQL Server's default port is **1433**. Ports like 30013 are
  non-standard (30013 is normally a SAP HANA port) — confirm with the DBA
  which port the MSSQL instance actually listens on.

## Fixes applied (2026-06-12)

1. `pyodbc==5.1.0` re-enabled in `backend/requirements.txt` (was commented out
   → every MSSQL attempt failed with "pyodbc not installed").
2. `backend/Dockerfile` runtime stage now installs **msodbcsql18** from
   Microsoft's Debian 12 repo (the code requests "ODBC Driver 18 for SQL
   Server"; the image previously only had generic unixODBC).
3. `TrustServerCertificate` changed `no` → `yes` (self-signed certs), and
   `Encrypt` now honors `is_tls` instead of being hardcoded.
4. Credential blob built with `json.dumps` instead of an f-string (passwords
   with quotes/backslashes previously produced corrupt, undecryptable blobs).
5. The discovery worker's duplicated (and equally broken) connection string
   was replaced with the shared `build_mssql_conn_str()`.

**After pulling these changes, rebuild the images** — pyodbc and the ODBC
driver bake into the image: `docker compose build && docker compose up -d`.

## Verifying a connection

### Quick reachability check (any machine)

```bash
nc -vz <host> <port>      # must print "succeeded" before anything else can work
```

The machine running the backend (or the test) must be on the same network /
VPN as the SQL Server. A `192.168.x.x` address is LAN-only.

### Live integration test

`backend/tests/integration/test_mssql_live.py` — skipped automatically unless
credentials are provided via environment, so it never runs in CI by accident
and no passwords live in the repo:

```bash
cd backend
export MSSQL_TEST_HOST=192.168.162.4
export MSSQL_TEST_PORT=30013
export MSSQL_TEST_DB=MEGATRADE_LIVE
export MSSQL_TEST_USER=sa
export MSSQL_TEST_PASSWORD='<password>'
pytest tests/integration/test_mssql_live.py -m integration --no-cov -rs
```

It verifies: connect + `@@VERSION`, correct database selected, catalog access
(needed by the discovery crawler), and presence of SAP B1 core tables
(`OCRD`, `OINV`, `ORDR`, `OITM`).

To run it inside the deployed backend container (which has pyodbc + the ODBC
driver and is usually on the right network):

```bash
docker compose exec -e MSSQL_TEST_HOST=... -e MSSQL_TEST_PORT=... \
  -e MSSQL_TEST_DB=... -e MSSQL_TEST_USER=... -e MSSQL_TEST_PASSWORD=... \
  api pytest tests/integration/test_mssql_live.py -m integration --no-cov -rs
```

### Via the API / UI

Create the connection in the onboarding wizard or Connections page, then:

```bash
curl -X POST http://localhost:8000/api/v1/connections/<id>/test
```

Returns `{success, latency_ms, db_version, is_read_only}` or
`{success: false, error}`.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `pyodbc not installed` | Image built before the fix | `docker compose build` |
| `Can't open lib 'ODBC Driver 18 for SQL Server'` | msodbcsql18 missing | Rebuild image (Dockerfile installs it) |
| `Login timeout expired` / connection timed out | Host/port unreachable (wrong network, firewall, SQL Browser off, TCP disabled) | `nc -vz host port`; enable TCP/IP in SQL Server Configuration Manager; check port |
| `Login failed for user` | Wrong credentials or SQL auth disabled | Verify user; enable mixed-mode authentication |
| `SSL Provider: certificate verify failed` | Would occur with `TrustServerCertificate=no` | Already handled — builder sets `yes` |
| `Circuit breaker is open` | Repeated recent failures to this connection | Wait ~60s for the breaker to close, fix root cause first |

## Related tests

- `backend/tests/unit/test_mssql_connection.py` — connection-string builder
  (TLS flag, timeout, password escaping) and credential blob round-trip.
- `backend/tests/integration/test_mssql_live.py` — live connectivity (gated).
