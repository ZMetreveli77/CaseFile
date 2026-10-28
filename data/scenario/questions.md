# Scenario questions: Larkspur Payments

A small, fictional company document set modelled on the assignment's example: technical documentation, a change
log, incident reports and a monthly review. Upload the files in this folder and ask the questions below.

| File | Format | What it holds |
|---|---|---|
| `architecture-overview.md` | Markdown | Services, the card payment path, the 23:00 database backup |
| `change-log-2026-q1.csv` | CSV (one document per row) | Eight changes, with dates, services and approvers |
| `INC-2026-031-incident-report.md` | Markdown | 4 March: card payments delayed, caused by CHG-1203 |
| `INC-2026-036-postmortem.html` | HTML | 11 March: authorization timeouts, caused by CHG-1214 |
| `INC-2026-041-incident-report.pdf` | PDF | 24 March: payouts late (not card payments), caused by CHG-1222 |
| `INC-2026-044-incident-report.md` | Markdown | 2 April: refunds failing, cause **not known** |
| `march-2026-operations-review.json` | JSON | Monthly summary; **disagrees** with INC-2026-031 on the duration |
| `on-call-runbook.txt` | Text | Distractor: how incidents are handled, no facts about March |

## Questions and what a correct answer looks like

1. **Which system changes caused payment processing delays in March, which services were affected, and which
   documents confirm it?** (the assignment's example)
   - CHG-1203 (ledger-service connection pool 60 → 15) caused INC-2026-031 on 4 March: ledger-service,
     payment-gateway and merchant-portal affected. Sources: the incident report and change log row CHG-1203.
   - CHG-1214 (fraud model v4) caused INC-2026-036 on 11 March: fraud-scoring and payment-gateway affected.
     Sources: the postmortem and change log row CHG-1214.
   - Optional: CHG-1222 delayed *payouts* on 24 March (settlement-batch, ledger-db), but card payments were not
     affected, so a careful answer keeps it apart or leaves it out.
   - A conflict should be reported: the incident report says 2 h 14 min, the operations review about 3 h 40 min.
2. **რომელმა სისტემურმა ცვლილებებმა გამოიწვია მარტში გადახდების დამუშავების შეფერხება, რომელი სერვისები დაზიანდა და
   რომელი დოკუმენტები ადასტურებს ამას?** The same question in Georgian. The documents are in English, so the agent
   has to search in English.
3. **How long did the card payment delay on 4 March last?** Conflict: 2 hours 14 minutes (incident report) versus
   about 3 hours 40 minutes (operations review). Both must be shown, not one picked silently.
4. **What caused the refund failures on 2 April?** Not enough information: the report says the cause is still under
   investigation, and CHG-1230 is only a suspect. The system should say so, not name CHG-1230 as the cause.
5. **Who approved the change that caused the authorization timeouts on 11 March?** Two hops: the postmortem names
   CHG-1214, and the change log says Mariam Lomidze approved it.
6. **Why did the settlement run on 24 March finish late?** Joins the PDF report (CHG-1222 moved the run to 23:00)
   with the architecture overview (the backup at 23:00 holds table locks for about 40 minutes).
7. **How much revenue did Larkspur Payments lose because of the March incidents?** No document says, so the system
   should decline.

## Result of one run (2026-10-29, Gemini, `eval/check_scenario.py`)

The script indexes only this folder into an in-memory store (Qdrant Cloud is not touched) and asks the 7 questions.

| # | Outcome | Notes |
|---|---|---|
| 1 | Answered: CHG-1203, CHG-1214, CHG-1222 | Right changes, services and documents, each claim cited. It counts CHG-1222 (late *payouts*) as a payment delay without saying card payments were unaffected. It didn't mention the duration conflict, which this question doesn't need. |
| 2 | Answered (Georgian question) | Same three changes. It searched once in Georgian, then in English. The answer is in Georgian, the claims in English. One flaw: the "documents that confirm it" claim also cites change log row 5 (CHG-1219), which is unrelated. |
| 3 | Answered with a conflict | 2 h 14 min from the incident report; the 3 h 40 min in the operations review is shown as a conflict, citing both. |
| 4 | "Still under investigation" | Says CHG-1230 is only a possible cause, not confirmed. No invented cause. |
| 5 | Mariam Lomidze | Two hops: postmortem → CHG-1214 → change log row. |
| 6 | "It overlapped with the database backup" | Correct but short: one search, cites the PDF report. It doesn't name CHG-1222. |
| 7 | Declined | Four searches, then "the documents do not contain any information about how much revenue was lost". |
