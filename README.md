# Moneten Extensions

This repository is the catalog of community extensions for [Moneten](https://github.com/MonetenApp/Moneten), an open-source money app for macOS.

An extension connects Moneten to a service that has no FinTS access: a credit card, PayPal, a broker, a foreign bank, or a bank whose login changes often. Extensions are written in Lua 5.4 against an API that is compatible with the [MoneyMoney web banking API](https://moneymoney.app/api/webbanking/), so most existing MoneyMoney extensions run unchanged.

## Status

The catalog is being built for Moneten v0.1. Nothing can be installed from here yet. The plan and its decisions live in the [Moneten repository](https://github.com/MonetenApp/Moneten).

## How the catalog works

- **One folder per extension.** It holds the Lua script or scripts, a manifest, a README, a recorded test run, and a license.
- **Each extension is a unit.** Moneten installs and updates it as one package.
- **Checks run automatically.** Every pull request runs automated checks:
  - no forbidden functions;
  - every host the extension contacts is listed in its manifest;
  - the recorded test passes;
  - the license is open source;
  - the code is readable.
- **A maintainer approves.** Every new extension and every update needs one maintainer's approval. A new host needs explicit sign-off.
- **The index is signed.** Moneten checks the signature and the SHA-256 of every file before it installs or runs an extension.
- **Updates that ask for more rights wait.** An update that adds hosts or login fields waits until the user confirms it in the app.

## Rules for extensions

- Extensions only read. They fetch accounts, balances, transactions, and holdings. They never send payments.
- Extensions contact only the hosts in their manifest, over HTTPS.
- Login data goes only to the service it belongs to. No tracking, no secrets in logs, no passwords in `LocalStorage`.
- The source is readable and has an open-source license that is compatible with the GPL. We recommend MIT.
- Each extension names a maintainer. An extension that fails and gets no answer from its maintainer within 90 days is marked as unmaintained, and someone else can take it over.

## Contribute

[Contributing](CONTRIBUTING.md) says how to submit an extension and run the checks. [Governance](GOVERNANCE.md) says how the review, the signing, and the states of a package work.

## License

The tooling and documentation of this repository are under the [MIT License](LICENSE). Each extension carries its own license in its folder.
