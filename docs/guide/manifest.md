# Manifest

Each catalog package has a `manifest.json` in its folder. Moneten reads it before it installs the package and shows the user the hosts, the login fields, and the license. [`schema/manifest.schema.json`](../../schema/manifest.schema.json) is the formal definition. The check `schema` of the catalog compares each manifest with it.

This is the manifest of the [tutorial package](tutorial/):

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

A catalog manifest must have all 11 fields, and no other field. A manifest must not name a key two times. The sections below give one example for each field.

## `id`

The name of the package folder in `extensions/`. It has lower-case letters and digits, with single hyphens between words, and at most 64 characters. It must be the same as the name of the folder, and it never changes.

```json
{"id": "my-bank"}
```

## `name`

The name that the Extensions window shows, with 1 to 60 characters.

```json
{"name": "My Bank"}
```

## `version`

The version of the package. It has one to three numbers with dots between them, such as `2.31`. Each change to a file of the package, other than the files in `recording/`, needs a higher version. The check `version` compares the version with `main`. A published version never changes.

```json
{"version": "2.31"}
```

## `description`

One sentence that tells what the extension fetches, with 1 to 200 characters.

```json
{"description": "Fetches balances and transactions of current accounts and credit cards from My Bank."}
```

## `files`

The Lua files of the package in load order. Each name has only letters, digits, underscores, and hyphens before `.lua`. List each file one time. All files run in the same Lua state.

```json
{"files": ["Helpers.lua", "MyBank.lua"]}
```

A MoneyMoney script with a space in its name, such as `My Bank.lua`, gets a new name, such as `My-Bank.lua`.

## `hosts`

Each host that the extension contacts, as an exact host name in lower case. Write no scheme, no port, no path, no wildcard, and no IP address. List the host of a browser login too, also when the script sends no request to it. A redirect target is a contact, so list it too.

```json
{"hosts": ["api.mybank.example", "login.mybank.example"]}
```

`mybank.example` does not include `api.mybank.example`. Each name in the list allows exactly one host. A new host in a pull request needs the label `hosts-approved` from a maintainer. Refer to [Hosts and redirects](reference.md#hosts-and-redirects).

## `services`

Each service that the script registers in `WebBanking{services = ...}`, with the labels of its login fields. Each service has a `name` with 1 to 60 characters, and a `login` list with 1 to 4 fields. A service name must occur only one time.

Each login field has a `label` with 1 to 40 characters. Set `secret` to `true` for a field that must not show what the user types, such as a password. `secret` is `false` when you do not set it. The script gets the fields in the sequence of the list.

```json
{
  "services": [
    {
      "name": "My Bank",
      "login": [
        {"label": "Customer number"},
        {"label": "PIN", "secret": true}
      ]
    },
    {
      "name": "My Bank Business",
      "login": [
        {"label": "API key", "secret": true}
      ]
    }
  ]
}
```

`InitializeSession(protocol, bankCode, username, reserved, password)` gets the first field in `username` and the second field in `password`. It gets the third field as its fourth argument, in place of `reserved`. It gets the fourth field as a sixth argument. `InitializeSession2` gets all fields in `credentials`, in the sequence of the list.

## `kinds`

The kinds of data that the extension fetches. The Extensions window shows them. Use each kind one time.

| Kind | The extension fetches |
| --- | --- |
| `balances` | the balance of each account |
| `transactions` | the transactions of each account |
| `securities` | the securities of a portfolio |
| `statements` | account statements as PDF files, with `FetchStatements` |

```json
{"kinds": ["balances", "transactions", "securities"]}
```

## `apiVersion`

The lowest value of `MM.apiVersion` that the extension needs, an integer of 1 or more. Moneten 0.1 has API version 1. A Moneten with a lower API version does not load the extension. It tells the user to update the app.

```json
{"apiVersion": 1}
```

## `license`

The SPDX identifier of the license in the `LICENSE` file of the package. The catalog accepts only these licenses, because each one is compatible with the GPL:

`MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `Apache-2.0`, `MPL-2.0`, `LGPL-2.1-or-later`, `LGPL-3.0-or-later`, `GPL-3.0-or-later`.

```json
{"license": "BSD-3-Clause"}
```

The check `license` compares `LICENSE` with the SPDX text of that license. Only the names and the years can be different.

## `maintainer`

The person who answers failure reports for the package. `name` has 1 to 100 characters. `github` is the GitHub login without `@`.

```json
{"maintainer": {"name": "Erika Mustermann", "github": "erika-mustermann"}}
```

When the maintainer does not answer a reproducible failure for 90 days, the package becomes unmaintained. Another author can then adopt it. Refer to [Updates and adoption](submit.md#updates-and-adoption).

## Manifest of a file install

A user can install a single `.lua` file without the catalog. A manifest with the same base name can go next to it, such as `MyBank.json` next to `MyBank.lua`. It then sets the hosts and the login labels. A file install can leave out any field. Without `hosts`, Moneten asks the user before each new host. Without a manifest, the login fields are "Username" and "Password".
