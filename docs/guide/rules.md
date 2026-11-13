# Rules

Each rule is a question about the script and its manifest. A catalog package must get "yes" for each question. The column "Check" names the check that tests the rule. The job `checks` runs `tools/check_package.py`, and each finding starts with the name of its rule, such as `host`. A rule with "Maintainer" has no automatic check, or an automatic check that a person must confirm. The maintainer reads the script for each rule.

Run the checks on your Mac before you open a pull request. [Contributing](../../CONTRIBUTING.md#run-the-checks-on-your-mac) tells how.

## Rules for each package

| # | Question | Check |
| --- | --- | --- |
| 1 | Does the script only read data, and does it send no payment? | Maintainer. Moneten never calls `SubmitPayment` or `FetchScheduledPayments`. |
| 2 | Does `hosts` in the manifest list each host that the script contacts, also the host of a browser login? | `host` in `checks`. The finding `new-host` marks each host of a new package and each new host of an update. It needs the label `hosts-approved` in `maintainer sign-off`. |
| 3 | Does each address in the script start with `https://` and name its host in the string? | `host` in `checks` |
| 4 | Does the script send login data only to hosts of the service that the login belongs to? | Maintainer, with the label `hosts-approved` |
| 5 | Is the script free of tracking, such as a request to an analytics service or a counter? | Maintainer |
| 6 | Does the script keep login data, cookies, and tokens out of `print`, `MM.printStatus`, and error messages? | Maintainer |
| 7 | Does the script keep passwords and PINs out of `LocalStorage`? | Maintainer |
| 8 | Does the script use only functions that Moneten gives? It does not use `os` other than `os.time`, `os.date`, `os.clock`, and `os.difftime`, and it does not use `load`, `loadstring`, `dofile`, `loadfile`, `require`, `debug`, `package`, or `string.dump`. | `forbidden` in `checks` |
| 9 | Does the script read globals only by their names, without `_ENV` as a value and without `_G` other than `_G.name` or `rawget(_G, "name")`? | `forbidden` in `checks` |
| 10 | Does the script work when `io.open` is `nil`? | Maintainer, with the label `io-acknowledged`. The finding `io` in `checks` shows each use of `io`. |
| 11 | Is each Lua file readable Lua 5.4 source in UTF-8, without bytecode? | `syntax` and `obfuscation` in `checks` |
| 12 | Is each line at most 500 characters? | `obfuscation` in `checks` |
| 13 | Does each function stay below the limits for encoded data: at most 200 escaped bytes, at most 300 characters of hex or Base64, at most 64 bytes as numbers in calls such as `string.char`, and no text that looks encrypted? | `obfuscation` in `checks` |
| 14 | Does `manifest.json` match the [schema](manifest.md), with an `id` that is the name of the folder and each service name only one time? | `schema` in `checks` |
| 15 | Does each service of `WebBanking{services = ...}` have an entry in `services` of the manifest, with the login fields that the script reads? | Maintainer |
| 16 | Does the folder hold only `manifest.json`, `README.md`, `LICENSE`, the Lua files in `files`, `recording/fixture.json`, and `recording/expected.json`, all as regular files? | `layout` in `checks` |
| 17 | Is `license` on the allowlist, and is `LICENSE` the SPDX text of that license with only names and years filled in? | `license` in `checks` |
| 18 | Does `ext test` replay `recording/fixture.json` and get `recording/expected.json`? | `ext-test` in the job `ext test`, with the `ext` of the commit in `tools/ext.lock`. |
| 19 | Does the recording hold only the sample IBAN `DE02120300000000202051` and email addresses on `example.com`, `example.org`, or `example.net`? | `personal-data` in `checks` |
| 20 | Are the names, account numbers, and amounts in the recording made up? | Maintainer |
| 21 | Does `README.md` tell which service the package is for and which accounts it fetches? | Maintainer |

## Rules for each change

| # | Question | Check |
| --- | --- | --- |
| 22 | When a file of the package other than the recording changed, is `version` higher than on `main`? | `version` in `checks` |
| 23 | Does the change keep each package folder that `main` has? To stop a package, mark it `withdrawn` in `status.json`. | `removed` in `checks` |
| 24 | When the change touches `tools/`, `.github/`, or `schema/`, did a maintainer read that change? | Maintainer. `CODEOWNERS` makes the review a requirement. |

## What the checks cannot find

The checks read the script but do not run it. They cannot find a host or a function name that the script makes at run time. They cannot see what a host does with the data that the script sends. The runtime of Moneten is the security boundary. It removes the functions of rule 8 and refuses each host that is not in the manifest. [Governance](../../GOVERNANCE.md#what-the-checks-cannot-catch) lists what the maintainer must read for.
