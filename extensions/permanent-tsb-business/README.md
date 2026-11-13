# Permanent TSB Business

Fetches the balances and the transactions of the business current accounts at [Permanent TSB](https://www.permanenttsb.ie) from the business web banking at `www.business24.ie`. It fetches booked and pending transactions.

## Login

- **Login number**: the login number of the business web banking.
- **Password-PAN**: the password, a minus sign, and the six-digit PAN, such as `password-123456`. The script asks the web banking which three digits of the PAN it needs and sends only those.

## Source

The script is `Permanent TSB Business.lua` 1.05 by Jan Münnich, unchanged, from <https://github.com/janmuennich/MoneyMoney-Permanent-TSB-Business> at commit `dd2bf5d3f8eb7d754bbba78e7e33d8ffeaf0401d`. Its name in this package is `Permanent-TSB-Business.lua`, because a catalog file name has no spaces. SHA-256: `a6ce11072708a7bfd374d23674aff27b66a81f1696d4344f4941aaddb99af833`.

The recording is written by hand from the requests that the script makes. No real account was used. All names, numbers, and amounts are made up.
