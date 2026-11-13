# From MoneyMoney to Moneten

Most MoneyMoney extensions run in Moneten without a change to the script. To put one into the catalog, you add a manifest, a README, a license, and a recording. This page does these steps for Monzo 0.91, the signed copy of the [Monzo extension](https://github.com/diederich/moneymoney-monzo) by Stephan Diederich.

You need `ext` ([Install ext](tutorial.md#install-ext)) and a fork of this repository ([Fork the repository](submit.md#fork-the-repository)).

This walkthrough needs an `ext` that has the change of [MonetenApp/Moneten#102](https://github.com/MonetenApp/Moneten/pull/102). That pull request is not merged yet. Monzo builds the query of a request with `pairs()`, so the sequence of its parameters changes from run to run. An `ext` without that change compares the query as it is, and the replay can miss a request. Build `ext` from the commit that merges #102, or from a later commit of `main`.

## Step 1: Get the script

1. Download the signed copy from the MoneyMoney extensions page:

	```sh
	mkdir -p extensions/monzo
	curl -fsSL -o extensions/monzo/Monzo.lua https://moneymoney.app/extensions/diederich/Monzo.lua
	shasum -a 256 extensions/monzo/Monzo.lua
	```

	The SHA-256 of version 0.91 is `614ee61ee0fd4eaf8be0ebac5f94d866edce23d33271f99ac3f6ed241695f0a0`. If you see a different value, the page has a different version. Compare it with the repository of the author.

2. Make sure that the file name has only letters, digits, underscores, and hyphens before `.lua`. `Monzo.lua` is correct. Rename a file such as `Permanent TSB Business.lua` to `Permanent-TSB-Business.lua`.

Do not change the script. The last line, `-- SIGNATURE: ...`, is the signature of MoneyMoney. Moneten ignores it, because it checks the signed index of the catalog.

## Step 2: Find the hosts

Find each address in the script:

```sh
grep -n '://' extensions/monzo/Monzo.lua
```

The addresses that the script contacts are:

- `https://api.monzo.com/...` is the API.
- `https://auth.monzo.com/` is the page of the browser login in `challenge`.

`moneymoney-app://oauth` is the redirect address that ends the browser login. Moneten closes the window there and does not contact it. Do not put it in `hosts`. The links to `monzo.com/docs` are in comments, so the script does not contact them.

## Step 3: Find the login fields

MoneyMoney keeps the labels of the login fields in its own database. Moneten reads them from the manifest. Find where the script reads the login values:

```lua
function InitializeSession2(protocol, bankCode, step, credentials, interactive)
  ...
  if step == 1 then
    clientId = credentials[1]
    clientSecret = credentials[2]
```

The first field is the client ID of a Monzo developer client, and the second field is its secret. The README of the author tells this too. The service name is `BANK_CODE`, which is "Monzo".

## Step 4: Write the manifest

Write `extensions/monzo/manifest.json`:

```json
{
  "id": "monzo",
  "name": "Monzo",
  "version": "0.91",
  "description": "Balances and transactions of Monzo current and joint accounts through the Monzo API, with an OAuth login in the browser.",
  "files": ["Monzo.lua"],
  "hosts": ["api.monzo.com", "auth.monzo.com"],
  "services": [
    {
      "name": "Monzo",
      "login": [
        {"label": "Client ID"},
        {"label": "Client secret", "secret": true}
      ]
    }
  ],
  "kinds": ["balances", "transactions"],
  "apiVersion": 1,
  "license": "MIT",
  "maintainer": {"name": "Your Name", "github": "your-github-login"}
}
```

- `version` is the `version` of `WebBanking{}`.
- `kinds` follows from the script. It returns balances and transactions, and no securities or statements.
- `license` is the license of the author. The repository of the author has an MIT `LICENSE` file.
- `maintainer` is the person who answers failure reports. Put your own name and GitHub login. If you are not the author, tell the author in the pull request.

## Step 5: Add the license and the README

1. Copy the `LICENSE` file of the author into `extensions/monzo/LICENSE`. For Monzo, it is the MIT text with "Copyright (c) 2018 Stephan Diederich".
2. Write `extensions/monzo/README.md`. Tell which accounts the package fetches, and where the user gets a client ID and a secret. Give the name and the source of the script.

## Step 6: Record and test

The recording needs a real login, so only an owner of a Monzo account can make it.

1. Record one run:

	```sh
	mkdir -p extensions/monzo/recording
	ext record extensions/monzo extensions/monzo/recording/fixture.json
	```

	`ext` asks for "Client ID" and "Client secret". For the browser login, it prints the URL of `auth.monzo.com`. Then it asks for the address at the end of the login.

2. Get the address at the end of the login:

	1. Open the developer tools of your browser and select the Network tab. In Safari, first turn on **Show features for web developers** in the **Advanced** settings.
	2. Open the URL from `ext` in the same window and log in.
	3. At the end, Monzo redirects to `moneymoney-app://oauth?code=...&state=...`. The browser cannot open this address and does not show it in the address bar. In the Network tab, find the request whose answer redirects there. Copy the full address from the `Location` header of that answer.
	4. Paste the address into `ext` and push Return. `ext` does not show what you paste.

	CAUTION: If MoneyMoney is installed, the browser can ask to open MoneyMoney. Click **Cancel**. Otherwise macOS gives the address to MoneyMoney, MoneyMoney uses the code, and the code does not work for `ext`.

3. Replace your account data in the fixture, as [Replace your account data](submit.md#replace-your-account-data) tells.
4. Write the expected file and run the test:

	```sh
	ext test --update extensions/monzo extensions/monzo/recording/fixture.json extensions/monzo/recording/expected.json
	ext test extensions/monzo extensions/monzo/recording/fixture.json extensions/monzo/recording/expected.json
	```

	You see `PASS 2 accounts, 5 transactions` for a recording with two accounts and five transactions.

## Step 7: Run the checks

```sh
python3 tools/check_package.py extensions/monzo
```

You see two warnings and no failure:

```
extensions/monzo/Monzo.lua:79: host: the host of moneymoney-app://oauth cannot be determined. Write the host into the string so the check can compare it with the manifest. Only a warning, because the string goes into MM.urlencode, so it is a value inside a request and not an address the script contacts.
extensions/monzo/Monzo.lua:94: host: the host of moneymoney-app://oauth cannot be determined. Write the host into the string so the check can compare it with the manifest. Only a warning, because the string goes into MM.urlencode, so it is a value inside a request and not an address the script contacts.
Checked 1 package(s): 0 failing, 2 other. ext test skipped, no ext binary.
```

The warnings are correct. The redirect address is a value in the request, not a host. The maintainer reads these lines in the review.

Then open the pull request, as [Open the pull request](submit.md#open-the-pull-request) tells.

## Differences to look for in other scripts

Most scripts need no change. Change a script only for these points, and tell the author:

- The script reads a file with `io.open`, or calls `os.execute`, `require`, or `load`. Moneten does not give these functions. Refer to [Lua runtime](reference.md#lua-runtime).
- The script contacts a host that it computes at run time, such as a host from a response. List each possible host in `hosts`. When the list is not known, the package cannot go into the catalog.
- The script ends a browser login at an address other than the three in [Browser login](reference.md#browser-login).
- The script calls a function that the API page does not document. Refer to [Names that the API page does not document](reference.md#names-that-the-api-page-does-not-document).
