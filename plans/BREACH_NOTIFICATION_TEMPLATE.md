# Data Breach Notification Template

> **Status: pre-launch draft.** olivia must have any actual breach
> notification reviewed by a lawyer before sending — laws vary by
> state and the notification's specific wording can affect liability.

## When to use this template

Send this template **only** when both are true:
1. There's been an actual or strongly-suspected data breach
2. The breach involved personal information of users (email
   addresses, account state, login records, vote history linked to
   identifiable accounts)

If only anonymous voter cookies were exposed (no email / user_id
linkage), the legal notification requirement does not apply — but
publishing a transparency note may still be the right thing to do.

## Timeline obligations

| State | Deadline (from discovery) | Source |
|---|---|---|
| California | 45 days max | CA Civil Code § 1798.82 |
| New York | "Most expedient time without unreasonable delay" | NY GBL § 899-aa |
| Texas | 60 days | TX Bus & Com Code § 521.053 |
| Florida | 30 days | FL Stat. § 501.171 |
| Maryland | 45 days | MD Comm Law § 14-3504 |
| Most other states | 30-60 days | various |
| Federal (under-13 users) | "Without delay" | COPPA § 6502(b)(2) |

**TeenCivics privacy policy commits to 30 days.** Whichever is
stricter (state law or our policy) governs.

## Information that must be in the notification (most states)

- What happened (in plain language)
- What information was affected
- What we've done since (containment + remediation)
- What the user should do (change passwords, watch for fraud, etc.)
- How to contact us with questions
- Toll-free numbers for major credit reporting agencies (some states)

## Template

---

**Subject:** Important security notice from TeenCivics

Hi [first_name or "TeenCivics member"],

We're writing to let you know about a security incident that may
have affected your TeenCivics account. We're sorry, and we want to
be straight with you about what happened.

### What happened

On [date], we discovered that [brief description of incident — e.g.
"an unauthorized third party gained access to a copy of our user
database" or "a configuration error briefly exposed some accounts to
public view"].

We discovered the issue on [date discovered] and contained it on
[date contained]. The incident appears to have lasted from [start]
to [end].

### What information was affected

For accounts that were affected, the following information may have
been exposed:

- Email address
- Display name (if you set one)
- Tier and Vote balance
- A list of which Congressional bills you voted on, and how
- Login timestamps (within the last 90 days)

The following information was **NOT** affected:

- We don't store passwords. (TeenCivics uses magic-link email login
  and Google sign-in. There are no TeenCivics passwords to steal.)
- We don't collect real names, addresses, phone numbers, or
  date-of-birth.
- We don't share data with advertisers or political organizations.
  None of that was exposed because we don't collect it.

### What we've done

Since discovering the incident, we have:

- [Specific containment actions — e.g. "rotated our security keys
  so existing sessions are invalidated and any stolen credentials
  no longer work"]
- [If credentials were rotated] **All TeenCivics users are now
  signed out and need to log in again.** Use the "magic link" or
  Google sign-in as normal.
- [Specific remediation — what we changed to prevent recurrence]
- Notified [law enforcement / state regulators / etc.] as required

### What you should do

- **Log in again** using your usual magic link or Google sign-in
- **If you used the same email password as for another service**
  (you don't have one with us, but in case the exposed email led
  someone to guess another service's password), update that
  service's password
- **Be alert for phishing emails** that pretend to be from
  TeenCivics or that reference your civic activity. We will only
  ever email you from `@teencivics.org`. We will never ask you to
  click a link to "verify" your account outside of the standard
  magic-link login flow.

You do not need to:

- Freeze credit (we never had your financial info)
- Cancel cards (we never had card data)
- Take any other action — there's nothing financial at risk

### How to contact us

If you have questions, concerns, or want more details about what
your account contained:

**Email**: contact@teencivics.org

We'll respond personally within 48 hours.

We will also publish a full incident report at
`teencivics.org/security/incident-[date]` within 30 days of this
notification.

### Our commitment

We're sorry this happened. Civic engagement should be safe. We're
committed to:

- Honesty about what went wrong
- Concrete steps to prevent recurrence
- Continuing to never sell, share, or monetize your individual data

If you decide this incident means TeenCivics isn't trustworthy
enough for you anymore, you can delete your account at
`teencivics.org/account/delete`. No hard feelings. We hope you'll
stick around.

— Liv Skeete
Founder, TeenCivics
contact@teencivics.org

---

## Internal checklist before sending

- [ ] Lawyer has reviewed the specific wording
- [ ] All affected user emails have been compiled and verified
  (don't send to deleted accounts; don't send to users who weren't
  actually affected)
- [ ] Email is being sent from a domain users recognize
  (`@teencivics.org`, not from Resend's bare domain)
- [ ] An incident page at the URL referenced in the email is ready
  to go live (drafted, even if "more details coming")
- [ ] State regulator notifications (where required) are queued
- [ ] Federal regulator notifications (if any under-13 user data
  was involved) are queued
- [ ] Social media post drafted for `@TeenCivics`, brief and
  matching the email tone
- [ ] FAQ document drafted for the predictable follow-up questions
- [ ] Whoever is monitoring contact@teencivics.org has been told to
  expect a volume spike and given response templates

## What state-specific notifications look like

Several states require notice to the state Attorney General when
breaches affect more than N residents of that state (typically 500
or 1000). The procedure varies — most have a web form. As of 2026:

- California AG: oag.ca.gov/privacy/databreach
- New York AG: ag.ny.gov/internet/data-breach
- Texas AG: ag.texas.gov
- Maryland AG: marylandattorneygeneral.gov/Pages/IdentityTheft

When the time comes, generate the list of affected users by state
(from the breach scope) and submit per state where the threshold
applies.

---

## Maintenance

Review this template every 6 months. Laws change. If a real
notification ever gets sent, update this template with any
improvements learned the hard way.
