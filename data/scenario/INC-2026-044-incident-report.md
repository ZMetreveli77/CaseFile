# Incident report INC-2026-044: refunds failing on 2 April 2026 (draft)

Larkspur Payments (fictional demo data). Severity: SEV-3. Incident commander: Nino Beridze. Status: open.

## Summary

On 2 April 2026, from 08:05 to 10:50 UTC, refund requests from the merchant portal failed with "internal error".
Merchants could not issue refunds during this time. Card payments and payouts were not affected.

## Affected services

- **refund-service**: returned errors for most refund requests.
- **merchant-portal**: showed "internal error" on the refunds page.

## Root cause

Still under investigation. Restarting refund-service at 10:45 UTC stopped the errors. The refund-service
upgrade to version 2.8 (CHG-1230, 1 April) is one possible cause, but the team has not been able to confirm it:
the same version ran without errors for 20 hours before the incident. The report will be updated when the
cause is known.
