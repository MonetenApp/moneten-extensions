# Governance

This page says who decides what enters the catalog, and what happens to a package after it is published.

## Review

Every pull request runs the workflow `check`. Its job `checks` fails on:

- a function that Moneten removes from the Lua runtime, such as `os.execute`, `require`, `load`, or `debug`;
- an `https://` address whose host is not in the manifest, and any `http://` address;
- a failed replay of the recording with `ext test`;
- a license outside the allowlist, or a `LICENSE` file that does not match the manifest;
- obfuscated code: bytecode, a line over 500 characters, a long escaped byte string, or a long string that looks encrypted;
- an IBAN or an email address in the recording that is not sample data;
- a manifest that does not match `schema/manifest.schema.json`.

A maintainer then reads the change. One maintainer approves each new package and each update. `CODEOWNERS` makes that approval a requirement for every file in the repository, the tools and workflows included.

Two findings do not fail `checks`, because only a person can judge them. The job `maintainer sign-off` fails until a maintainer sets a label:

| Finding | Label | What the maintainer checks |
| --- | --- | --- |
| The pull request adds a host to a manifest, or adds a new package. | `hosts-approved` | The host belongs to the service, and the script sends login data only there. |
| A script reads `io`. | `io-acknowledged` | The script works when `io.open` is `nil`. Moneten gives scripts an `io` table without functions. |

Only maintainers can set labels. Adding or removing a label runs every job again.

The checks are a first filter. Moneten enforces the same limits when the script runs: it removes the same functions and refuses every host that the manifest does not list.

## Signing

The workflow `sign` runs on each push to `main` that changes what the app downloads. It waits until a maintainer approves the run in the environment `catalog-signing`. The index then gets the next version number, and the run publishes it with its signature. A published version of a package never changes. A changed file needs a higher version in the manifest, and the checks fail without one. [Set up the signing key](docs/set-up-signing.md) describes the environment and the key rotation.

## States of a package

`status.json` gives a package a state other than active. The index carries the state and its note to every installed copy.

| State | When | Effect in Moneten |
| --- | --- | --- |
| `blocked` | The package has a security problem. A maintainer blocks it at once, without waiting for the author. | It stops running. |
| `withdrawn` | The service closed, or the author asked to withdraw the package. | It stops running. |
| `unmaintained` | The package fails in a way that others can reproduce, and its maintainer did not answer for 90 days. | It keeps running with the note. |

A package folder is never deleted, because only an index entry can stop an installed copy. To remove a package, mark it `withdrawn`.

Anyone may adopt an unmaintained package. Open a pull request that fixes the failure, puts your name in `maintainer` of its manifest, and removes its entry from `status.json`.
