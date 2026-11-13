# Example Bank

This package is the reference package of the catalog. Example Bank is made up. Its hosts `www.bank.example` and `api.bank.example` use the reserved `.example` domain and do not exist.

The script logs in with a form post, reads the accounts and the transactions as JSON, and logs out. The recording in `recording/` replays one login with one account and four transactions. Its IBAN and its names are sample data.

The format of `recording/fixture.json` and `recording/expected.json` is provisional. The `ext` tool of the Moneten repository defines the final format. Until `ext` exists, the catalog checks read the recording only for personal data.
