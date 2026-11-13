# Tutorial: write your first extension

<!-- The maintainers have not confirmed the tutorial API yet. See the pull request that added this page. -->

This tutorial makes an extension for the fake bank of [SampleAPIs](https://github.com/jermbo/SampleAPIs). The API needs no login and no key, and all its data is made up. At the end, you have a package with one account and 12 transactions. Its recording replays with `ext test` without a network.

Each step ends with a command and the output that you see. The finished package is in [`tutorial/`](tutorial/).

## Before you start

You need:

- A Mac with macOS 15 or later.
- Xcode 16.3 or later, or the Swift 6.1 toolchain.
- A connection to the internet for steps 2 and 4.

Write the commands in a terminal. Each step starts in the same work folder.

## Install ext

`ext` runs, records, and tests an extension outside the app. It uses the same code as Moneten, so a script that works in `ext` works in the app.

There is no signed release of `ext` yet. Build it from a commit of `MonetenApp/Moneten` that the maintainers checked. The commit is `6fbfd21fbae4b580c2800182a9738b3099de1416`. When `tools/ext.lock` of this repository names a commit, use that commit.

1. Get the source:

	```sh
	git clone https://github.com/MonetenApp/Moneten.git moneten
	cd moneten
	git checkout --detach 6fbfd21fbae4b580c2800182a9738b3099de1416
	```

2. Make sure that you have the correct commit, and that it is on `main`:

	```sh
	git rev-parse HEAD
	git merge-base --is-ancestor HEAD origin/main && echo "on main"
	```

	The first command must print `6fbfd21fbae4b580c2800182a9738b3099de1416`. The second command must print `on main`. If one of them prints a different result, stop and open an issue.

3. Build `ext`:

	```sh
	swift build --disable-keychain -c release --product ext
	```

	The option `--disable-keychain` stops a Keychain prompt that SwiftPM can wait for without a message.

4. Put `ext` in your path and go back to the work folder:

	```sh
	export PATH="$PWD/.build/release:$PATH"
	cd ..
	ext --version
	```

	You see:

	```
	ext 0.1.0, API version 1
	```

`export` changes the path only in this terminal window. Write the line into `~/.zshrc` to keep it.

### When a release exists

The maintainers will publish a signed binary of `ext` with its SHA-256 in a release of `MonetenApp/Moneten`. This section will then replace the build steps with a download and a SHA-256 check.

## Step 1: Register the service

An extension is a folder with a Lua script and a manifest. The script tells Moneten which service it supports. The manifest tells Moneten which hosts the script contacts and which login fields it needs.

1. Make the folder:

	```sh
	mkdir tutorial
	```

2. Write `tutorial/manifest.json`:

	```json
	{
	  "id": "tutorial",
	  "name": "Sample Fake Bank",
	  "version": "1.0",
	  "description": "Fetches the made-up card transactions of the SampleAPIs fake bank.",
	  "files": ["Tutorial.lua"],
	  "hosts": ["api.sampleapis.com"],
	  "services": [
	    {"name": "Sample Fake Bank", "login": [{"label": "Any name"}]}
	  ],
	  "kinds": ["balances", "transactions"],
	  "apiVersion": 1,
	  "license": "MIT",
	  "maintainer": {"name": "Moneten maintainers", "github": "alexander-schneider"}
	}
	```

	Put your own name and GitHub login in `maintainer`. The API needs no login, but Moneten asks for at least one login field. The script does not use the value.

3. Write `tutorial/Tutorial.lua`:

	```lua
	WebBanking {
	  version = 1.0,
	  url = "https://api.sampleapis.com",
	  services = {"Sample Fake Bank"},
	  description = "Fetches the made-up card transactions of the SampleAPIs fake bank."
	}

	function SupportsBank(protocol, bankCode)
	  return protocol == ProtocolWebBanking and bankCode == "Sample Fake Bank"
	end

	function InitializeSession(protocol, bankCode, username, reserved, password)
	end

	function ListAccounts(knownAccounts)
	  return {
	    {
	      name = "Fake Bank Card",
	      accountNumber = "fakebank-1",
	      currency = "USD",
	      type = AccountTypeCreditCard
	    }
	  }
	end

	function RefreshAccount(account, since)
	  return {balance = 0, transactions = {}}
	end

	function EndSession()
	end
	```

	`WebBanking{}` registers the service. Moneten calls `SupportsBank`, `InitializeSession`, `ListAccounts`, `RefreshAccount` for each account, and `EndSession`, in this sequence.

4. Run the script:

	```sh
	ext run tutorial
	```

	`ext` asks for the field "Any name". Type a word and push Return. You see one account without transactions:

	```json
	{
	  "accounts" : [
	    {
	      "accountNumber" : "fakebank-1",
	      "balance" : 0,
	      "currency" : "USD",
	      "name" : "Fake Bank Card",
	      "transactions" : [

	      ],
	      "type" : "AccountTypeCreditCard"
	    }
	  ]
	}
	```

`ext run` also writes `tutorial.storage.json` next to the folder. That file holds `LocalStorage` between runs. Do not commit it.

## Step 2: Read the transactions

The API gives a list of transactions as JSON. Each item has a date, a description, a category, and an amount in `debit` or `credit`.

1. In `tutorial/Tutorial.lua`, add these two lines below `WebBanking{}`:

	```lua
	local api = "https://api.sampleapis.com/fakebank/accounts"
	local connection
	```

2. Replace `InitializeSession` with this code:

	```lua
	function InitializeSession(protocol, bankCode, username, reserved, password)
	  connection = Connection()
	end
	```

3. Replace `RefreshAccount` with this code:

	```lua
	local function parseDate(text)
	  local year, month, day = text:match("^(%d+)-(%d+)-(%d+)$")
	  return os.time{year = tonumber(year), month = tonumber(month), day = tonumber(day), hour = 12}
	end

	function RefreshAccount(account, since)
	  local content = connection:request("GET", api .. "?id_lte=12", nil, nil, {Accept = "application/json"})
	  local transactions = {}
	  local balance = 0
	  for _, row in ipairs(JSON(content):dictionary()) do
	    local amount = (tonumber(row.credit) or 0) - (tonumber(row.debit) or 0)
	    balance = balance + amount
	    local bookingDate = parseDate(row.transactionDate)
	    if bookingDate >= since then
	      table.insert(transactions, {
	        bookingDate = bookingDate,
	        name = row.description,
	        purpose = row.category,
	        amount = amount,
	        currency = "USD",
	        booked = true
	      })
	    end
	  end
	  return {balance = balance, transactions = transactions}
	end
	```

	`?id_lte=12` gets the first 12 items. Other users of SampleAPIs can add items, so the first 12 are the only items that do not change. A debit becomes a negative amount. `since` is the earliest date that Moneten asks for. For a new account it is 0.

4. Run the script again:

	```sh
	ext run tutorial
	```

	You see the account with a balance and 12 transactions. The first lines are:

	```json
	{
	  "accounts" : [
	    {
	      "accountNumber" : "fakebank-1",
	      "balance" : -113.24,
	      "currency" : "USD",
	      "name" : "Fake Bank Card",
	      "transactions" : [
	        {
	          "amount" : -100.84,
	          "booked" : true,
	          "bookingDate" : 1451559600,
	          "currency" : "USD",
	          "name" : "All Purpose Spray",
	          "purpose" : "Other Services"
	        },
	```

	`bookingDate` is a time in seconds since 1970, as the script returns it. The value depends on the time zone of your Mac.

If you see `-113.24` as the balance, the script works.

## Step 3: See the host limit

Moneten lets the script contact only the hosts in `hosts` of the manifest. `ext` uses the same limit.

1. In `RefreshAccount`, add this line above the line that starts with `local content`:

	```lua
	connection:request("GET", "https://www.sampleapis.com/", nil, nil, {})
	```

2. Run the script:

	```sh
	ext run tutorial
	```

	`ext` sends no request to `www.sampleapis.com`. It stops with exit status 2 and this message:

	```
	Fake Bank Card: Tutorial.lua:36: tutorial may not contact www.sampleapis.com, because its manifest does not list that host.
	```

3. Remove the line again.

A host name in the manifest must be exact. `api.sampleapis.com` does not let the script contact `www.sampleapis.com` or `sampleapis.com`. The [reference](reference.md#hosts-and-redirects) gives all the rules.

## Step 4: Record the run

A recording holds each request of a run and its answer. The catalog checks replay it, so a reviewer can see what the script does without your login.

```sh
mkdir tutorial/recording
ext record tutorial tutorial/recording/fixture.json
```

Type a word for "Any name". You see:

```
Recorded 1 request.
Replaced 1 username.
```

`ext` then gives two reminders. It replaces login data, cookies, and tokens with placeholders such as `{{username}}`. It does not replace names, IBANs, or amounts. This API gives only made-up data, so you need not change the recording. For a real service, read [Replace your account data](submit.md#replace-your-account-data) before you commit a recording.

## Step 5: Test the recording

`ext test` replays the recording without a network and compares the result with an expected file.

1. Write the expected file from the replay:

	```sh
	ext test --update tutorial tutorial/recording/fixture.json tutorial/recording/expected.json
	```

	You see the result, and then:

	```
	Wrote tutorial/recording/expected.json with 1 account, 12 transactions.
	```

2. Run the test:

	```sh
	ext test tutorial tutorial/recording/fixture.json tutorial/recording/expected.json
	```

	You see:

	```
	PASS 1 account, 12 transactions
	```

The recording holds the time and the time zone of the run. Thus the test gives the same result on each Mac and on each day.

3. Change one amount in `tutorial/recording/expected.json`, for example `-100.84` to `-100.48`, and run the test again. You see the difference and exit status 1:

	```
	/accounts/0/transactions/0/amount: expected -100.48, got -100.84
	```

	Change the amount back.

## Step 6: Finish the package

A catalog package also has a `README.md` and a `LICENSE`. Compare your folder with [`tutorial/`](tutorial/). Your folder then has these files:

```
tutorial/
  LICENSE
  README.md
  Tutorial.lua
  manifest.json
  recording/expected.json
  recording/fixture.json
```

Next:

- [Submit an extension](submit.md) tells how to put a package into the catalog.
- [Reference](reference.md) lists each difference from the MoneyMoney Web Banking API.
- [Manifest](manifest.md) describes each field of `manifest.json`.
- [Rules](rules.md) lists the questions that the review asks about each package.
