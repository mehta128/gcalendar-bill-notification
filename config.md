# Bill Agent Configuration

Edit this file to customize what the agent looks for and who gets notified.

---

## Keywords

The agent will match calendar events and tasks containing ANY of these words (case-insensitive).

```
bill
payment
due
invoice
subscription
rent
mortgage
insurance
utility
credit card
loan
EMI
tax
payroll
CIBC
Scotia
interac
```

---

## Email

```
to: 007halfbloodprince@gmail.com
from: 007halfbloodprince@gmail.com
subject: Bill & Payroll Reminder — {date}
smtp_host: smtp.gmail.com
smtp_port: 587
```

---

## Schedule

Change `time` to any 24-hour HH:MM you want the agent to run daily.
Change `timezone` to your local timezone.

```
time: 08:50
timezone: America/Toronto
```

---

## Notes

- Add or remove keywords one per line inside the fenced block above.
- Update `to:` and `from:` with your actual email addresses.
- The agent uses these keywords to filter tasks and calendar events — anything that does NOT match is ignored.
