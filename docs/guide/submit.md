# Submit an extension

This page tells how to put a package into the catalog, and what happens to it after that. [Governance](../../GOVERNANCE.md) is the full description of the review, the signing, and the states of a package.

## Fork the repository

1. On GitHub, open [MonetenApp/moneten-extensions](https://github.com/MonetenApp/moneten-extensions) and click **Fork**.
2. Clone your fork and make a branch:

	```sh
	git clone https://github.com/<your-login>/moneten-extensions.git
	cd moneten-extensions
	git switch -c add-my-bank
	```

3. Install the tools of the checks. You need Python 3.12, a C compiler, and OpenSSL 3:

	```sh
	python3 -m venv .venv
	source .venv/bin/activate
	tools/setup.sh
	```

You also need `ext`. [Install ext](tutorial.md#install-ext) tells how.

## Make the package

A package is a folder `extensions/<id>`. `<id>` has lower-case letters and digits, with single hyphens between words, such as `my-bank`.

```
extensions/my-bank/
  LICENSE
  MyBank.lua
  README.md
  manifest.json
  recording/expected.json
  recording/fixture.json
```

1. Copy `extensions/example` to `extensions/<id>`.
2. Replace `Example.lua` with your script. Put the name of each Lua file in `files` of the manifest, in load order.
3. Write the manifest. [Manifest](manifest.md) describes each field.
4. Put the text of your license in `LICENSE`. Use the SPDX text of the license in `license` of the manifest. Fill in only your name and the year.
5. In `README.md`, tell which service the package is for and which accounts it fetches. Tell what the user types into each login field.

The folder must not hold other files. Keep the file `<id>.storage.json` that `ext run` writes out of the package folder and out of git. This repository ignores files with that name.

## Record a run

The recording lets the checks and the maintainer replay your script without your login.

1. Record one run with your own login:

	```sh
	ext record extensions/my-bank extensions/my-bank/recording/fixture.json
	```

	`ext` asks for each login field. It replaces secrets with placeholders such as `{{password}}` and `{{cookie1}}`. The secrets are the login data, the answers to challenges, cookies, `Authorization` headers, and tokens. It then tells you the number of values that it replaced, by kind. No option turns this off.

2. Write the expected result and run the test:

	```sh
	ext test --update extensions/my-bank extensions/my-bank/recording/fixture.json extensions/my-bank/recording/expected.json
	ext test extensions/my-bank extensions/my-bank/recording/fixture.json extensions/my-bank/recording/expected.json
	```

	The second command must print `PASS` and exit with status 0.

`ext record` writes no fixture when the run fails. It also writes no fixture in these cases:

- A response holds a password with fewer than 8 characters, or a password of only digits, such as a PIN. The text around its placeholder can show the PIN. Make a recording where no response holds it.
- A request holds such a password inside a longer value, such as `from=2025-10-10` for the PIN `2025`.
- The replay needs a random value that the script used as a key. This is the key or the IV of `MM.aes256encrypt`, or the key of an HMAC.
- The replay of the fixture can make an AES or HMAC key again from the values in the fixture.
- The replay needs a random value. The script also used an AES or HMAC key that `ext` cannot trace to a recorded random value. Use `--keep-random` only when that value is no key, such as a PKCE verifier.

`ext record` keeps a random value only when an address of the recording holds it, or when the replay needs it. It names each value that it keeps with the request that holds it. Make sure that none of them is a secret. Of each other random value, the fixture holds only the kind and the length.

## Replace your account data

The fixture still holds your names, account numbers, IBANs, and amounts. Replace each of them with made-up data before you commit the files:

- Use the IBAN `DE02120300000000202051` for each IBAN. The check `personal-data` fails on any other valid IBAN.
- Use email addresses on `example.com`, `example.org`, or `example.net`.
- Replace names with made-up names, such as "Erika Mustermann".
- Replace account numbers, card numbers, and amounts with made-up values.
- Look for login data that the script hashed or encoded with other data, such as `MM.sha256(pin)`. `ext` cannot find it.

Replace each value in `fixture.json` and in `expected.json` together, and run `ext test` again. The script can send a value from a response again in a later request. Such a value must stay the same in both places.

## Run the checks

Run the tests and the checks of all packages. Then check your package with `ext test`:

```sh
BASE=origin/main tools/check-all.sh
python3 tools/check_package.py --base origin/main --ext "$(command -v ext)" extensions/my-bank
```

Each finding is one line with the file, the line, and the rule. [Rules](rules.md) lists each rule. A finding that needs a label, such as `new-host`, does not fail on your Mac. A maintainer sets the label in the review.

## Open the pull request

1. Commit the package and push the branch to your fork:

	```sh
	git add extensions/my-bank
	git commit -m "Add My Bank"
	git push -u origin add-my-bank
	```

2. On GitHub, open a pull request into `main` of `MonetenApp/moneten-extensions`.
3. In the description, tell which service the package is for and how you made the recording.

## The review

The pull request must pass three jobs:

- `checks` runs the tests of the tools and every check on every package.
- `ext test` replays each recording with `ext`. It runs when `tools/ext.lock` names a commit of `MonetenApp/Moneten`. Until then, GitHub shows it as skipped.
- `maintainer sign-off` fails until a maintainer accepts the findings that only a person can judge.

A maintainer then reads the change and approves it. Each new package and each update needs one approval of a maintainer.

### New hosts and io

`maintainer sign-off` needs a label for two findings:

| Finding | Label | What the maintainer checks |
| --- | --- | --- |
| The pull request adds a package, or adds a host to a manifest. | `hosts-approved` | Each host belongs to the service, and the script sends login data only there. |
| A script reads `io`. | `io-acknowledged` | The script works when `io.open` is `nil`. |

A label counts only for the commit that the maintainer read. The maintainer first approves the newest commit of the pull request, then sets the label. On a pull request of a maintainer, the author cannot approve. The author then leaves a review with **Comment** on the newest commit. The text of the review holds the word `sign-off`. Then the author sets the label.

When you push a new commit after the label, the label no longer counts. The maintainer must approve the new commit and set the label again, or run the job again.

## Publication

When a maintainer merges the pull request, the workflow `sign` waits for a maintainer to approve the signing run. The run signs the index and publishes the package at `https://extensions.monetenapp.com`. Moneten downloads the index at start and once a day.

## Updates and adoption

### Update a package

1. Change the files of the package.
2. Increase `version` in the manifest. The check `version` fails when a file other than the recording changed and the version did not increase. A published version never changes.
3. Record again when the requests changed, and run `ext test`.
4. Open a pull request, as for a new package.

Moneten installs an update without a question when it adds no host and no login field. An update that adds a host or a login field waits until the user confirms it in the app. Until then the old version runs. A new host also needs the label `hosts-approved` in the review.

### Unmaintained packages

Each package names a maintainer in its manifest. When a package fails in a way that others can reproduce, open an issue that names the maintainer. When the maintainer does not answer for 90 days, a maintainer of the catalog marks the package `unmaintained` in `status.json`. It keeps running in Moneten with a note.

### Adopt a package

Anyone can adopt an unmaintained package. Open a pull request with these changes:

1. It repairs the failure.
2. It puts your name and your GitHub login in `maintainer` of the manifest.
3. It increases `version`.
4. It removes the entry of the package from `status.json`.

### Blocked and withdrawn packages

A maintainer of the catalog blocks a package with a security problem at once, without a wait for its author. It stops in Moneten after the next download of the index. A package of a service that closed, or whose author asks for it, becomes `withdrawn` and also stops. A package folder is never deleted, because only an entry in the index can stop an installed copy.
