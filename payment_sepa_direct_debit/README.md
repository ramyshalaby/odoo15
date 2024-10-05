# Sepa Direct Debit

## Technical details

This module does not integrate with an API and, instead, allows to create SEPA Direct Debit mandates
from a custom payment form on the payment page. Mandates are linked to payment tokens; when used to
make a payment, they create `account.payment` records that must be sent to a bank to collect the
payment.

## Supported features

- Direct payment flow
- Tokenization with our without payment

## Testing instructions

SEPA Direct Debit doesn't have a test mode.
