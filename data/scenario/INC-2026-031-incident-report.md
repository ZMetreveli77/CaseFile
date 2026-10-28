# Incident report INC-2026-031: card payments delayed on 4 March 2026

Larkspur Payments (fictional demo data). Severity: SEV-2. Incident commander: Mariam Lomidze. Status: resolved.

## Summary

On 4 March 2026, from 09:12 to 11:26 UTC (2 hours 14 minutes), card payments were processed with long delays.
Payments were accepted by payment-gateway but waited up to 9 minutes before being recorded. 4,180 payments were
delayed. No payment was lost or charged twice.

## Affected services

- **ledger-service**: all instances ran out of database connections; payments queued inside the service.
- **payment-gateway**: requests piled up while waiting for ledger-service; the gateway's error rate stayed below 1%.
- **merchant-portal**: showed delayed payments as "pending" until they were recorded.

fraud-scoring and settlement-batch were not affected.

## Root cause

Change CHG-1203, deployed on 3 March, reduced the ledger-service connection pool from 60 to 15 connections per
instance. Traffic was low overnight, so the problem only appeared when the Tuesday morning peak started at 09:00
UTC: 15 connections per instance could not keep up and the pool was exhausted.

## Timeline (UTC)

- 09:12 alert: ledger-service queue length above 500.
- 09:40 on-call engineer found the pool exhausted on every instance.
- 10:55 the link to CHG-1203 was confirmed.
- 11:05 CHG-1203 rolled back (pool back to 60 connections).
- 11:26 the queue was empty; incident resolved.

## Follow-up actions

1. Load-test connection pool changes with peak traffic before deploying.
2. Alert on connection pool usage above 80%.
