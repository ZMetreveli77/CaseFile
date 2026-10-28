# Larkspur Payments: Payment Platform Architecture Overview

Owner: Platform Engineering. Last reviewed: 2026-02-15. Larkspur Payments is a fictional company; this document is demo data.

## Services

- **payment-gateway**: receives every card payment from merchants' checkouts. For each payment it first asks
  fraud-scoring for a risk score, then asks ledger-service to record the transaction. The gateway waits at most
  800 ms for fraud-scoring; if no score arrives in time, the payment is declined as "authorization timeout".
- **fraud-scoring**: returns a risk score from 0 to 100 for a payment. Runs the fraud model and calls the
  device-reputation lookup when the model needs it.
- **ledger-service**: writes every transaction to the PostgreSQL cluster `ledger-db`. Each instance keeps a pool of
  database connections; a payment waits in a queue when all connections in the pool are busy.
- **settlement-batch**: a nightly job that reads the day's transactions from `ledger-db` and creates merchant payouts.
- **refund-service**: handles refund requests from the merchant portal and writes them to ledger-service.
- **notification-service**: sends payment receipts and payout emails. It reads from a message queue, so a slowdown
  there does not delay payments.
- **merchant-portal**: the web application where merchants see payments, payouts and refunds.

## Dependencies on the payment path

A card payment depends on three services in order: payment-gateway → fraud-scoring → ledger-service (→ ledger-db).
A slowdown in any of the three delays or fails the payment. settlement-batch, refund-service and
notification-service are not on the card payment path.

## Maintenance windows

`ledger-db` takes a full backup every night at 23:00 UTC. The backup holds table locks for about 40 minutes, so
heavy jobs should not run on `ledger-db` between 23:00 and 23:45 UTC.
