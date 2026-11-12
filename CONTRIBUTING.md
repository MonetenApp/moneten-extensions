# Contributing

This page says how to submit an extension and how to run the checks before you open a pull request.

## Add a package

1. Copy `extensions/example` to `extensions/<id>`, where `<id>` is a lowercase name such as `my-bank`.
2. Replace `Example.lua` with your script. List every Lua file in `files` of `manifest.json`, in load order.
3. Fill in the manifest. `schema/manifest.schema.json` describes every field. List every host the script contacts as an exact name.
4. Put your license text in `LICENSE` and its SPDX identifier in `license`. The allowed licenses are MIT, BSD-2-Clause, BSD-3-Clause, ISC, Apache-2.0, MPL-2.0, LGPL-2.1-or-later, LGPL-3.0-or-later, and GPL-3.0-or-later.
5. Record one run of the script with `ext record` into `recording/fixture.json`, and save its result as `recording/expected.json`. Replace names, account numbers, and amounts that belong to you. Use the IBAN `DE02120300000000202051` and email addresses on `example.com`.
6. Open a pull request. Each later change to a file of the package needs a higher `version` in the manifest.

The `ext` tool comes from the [Moneten repository](https://github.com/MonetenApp/Moneten). Until it is released, the checks skip the replay of the recording.

## Run the checks on your Mac

You need Python 3.12, a C compiler, and OpenSSL 3. Run these commands in the repository:

```sh
python3 -m venv .venv
source .venv/bin/activate
tools/setup.sh
BASE=origin/main tools/check-all.sh
```

`tools/setup.sh` builds `luac` 5.4.8 into `.cache/` and installs the Python packages. `tools/check-all.sh` prints one line for each finding, with the file and the line. Set `EXT` to the path of an `ext` binary to also replay the recordings.

To check one package, run `python3 tools/check_package.py extensions/<id>`.

## Change the tools

The tools in `tools/` have tests in `tools/tests/`. Each rule has a failing package and the example package passes. `tools/check-all.sh` runs the tests first. A change to a check needs a test that fails without the change.

## Rules for maintainers

[Governance](GOVERNANCE.md) describes the review, the labels `hosts-approved` and `io-acknowledged`, and the states of a package.
