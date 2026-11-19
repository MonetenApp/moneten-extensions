# Monzo

Fetches the balances and the transactions of Monzo current accounts and joint accounts through the [Monzo API](https://docs.monzo.com). The login opens the Monzo login page in a browser window.

## Login

The Monzo API needs your own OAuth client from the Monzo developer portal, with the redirect URL `moneymoney-app://oauth`.

- **Client ID**: the ID of the OAuth client.
- **Client secret**: the secret of the OAuth client.

Then log in to Monzo in the browser window that Moneten opens.

## Source

The script is `Monzo.lua` 0.91 by Stephan Diederich, unchanged, the signed copy at <https://moneymoney.app/extensions/diederich/Monzo.lua>. The repository is <https://github.com/diederich/moneymoney-monzo>. SHA-256: `614ee61ee0fd4eaf8be0ebac5f94d866edce23d33271f99ac3f6ed241695f0a0`.

The recording is written by hand from the requests that the script makes. No real account was used. All names, numbers, and amounts are made up.
