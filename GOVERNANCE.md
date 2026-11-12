# Governance

This page says who decides what enters the catalog, and what happens to a package after it is published.

## Review

Every pull request runs the workflow `check`. Its job `checks` fails on:

- a function that Moneten removes from the Lua runtime, such as `os.execute`, `require`, `load`, or `debug`, and any use of `_ENV` other than reading a global by its name;
- an address with `://` whose host is not in the manifest or cannot be read from the script, and any `http://` address;
- a failed replay of the recording with `ext test`;
- a license outside the allowlist, or a `LICENSE` file that differs from the SPDX text of the license in the manifest in more than its names and years;
- obfuscated code: bytecode, a line over 500 characters, or a function whose strings hold more than 200 escaped bytes, more than 300 characters of hex or base64, more than 64 bytes passed as numbers to calls such as `string.char`, or text that looks encrypted;
- an IBAN or an email address in the recording that is not sample data;
- a manifest that does not match `schema/manifest.schema.json`;
- a symbolic link, a hard link, a FIFO, or a device anywhere in a package, and a symbolic link or a submodule anywhere in the repository. The checks read nothing of such a package, and the signing run refuses to publish.

A maintainer then reads the change. One maintainer approves each new package and each update. `CODEOWNERS` makes that approval a requirement for every file in the repository, the tools and workflows included.

Two findings do not fail `checks`, because only a person can judge them. The job `maintainer sign-off` of the workflow `sign-off` fails until a maintainer sets a label. It runs the workflow and the tools as `main` has them, and reads the pull request only as data, so a pull request cannot change how it is judged:

| Finding | Label | What the maintainer checks |
| --- | --- | --- |
| The pull request adds a host to a manifest, or adds a new package. | `hosts-approved` | The host belongs to the service, and the script sends login data only there. |
| A script reads `io`. | `io-acknowledged` | The script works when `io.open` is `nil`. Moneten gives scripts an `io` table without functions. |

The job also fails, whatever the labels, when a schema, layout, or syntax error keeps the check from reading the hosts and the scripts of a package.

Only maintainers can set labels. A label counts only while a maintainer's approving review names the newest commit of the pull request, because a review records the commit it read. So approve the pull request first, then set the label, which runs the job again. A push after the sign-off needs a new approval: approve again, then remove the label and set it again, or re-run the job. On a pull request that a maintainer opened from a branch of this repository, the label counts without a review, because GitHub does not let authors approve their own pull requests.

Some addresses only produce a warning: a Lua pattern such as `"^https://"`, a string that goes into `MM.urlencode`, and an XML namespace or the OAuth redirect address. The warning gives the reason. The maintainer reads these lines too.

## What the checks cannot catch

The checks read the script without running it. They are a review aid, not the security boundary. The boundary is the runtime of Moneten: it removes the forbidden functions, gives `io` no functions, and refuses every request and redirect to a host that the manifest does not list, whatever the script computes.

The checks cannot see:

- a host or a function name that the script computes at run time, for example from a table, `string.reverse`, arithmetic, or data from a response;
- a host that a script appends to a declared host at run time, as in `"https://www.bank.example" .. suffix`;
- an index into a table with a computed key, such as `getmetatable("").__index[name]`;
- encoded data below the limits, or split over several functions;
- bytes that reach `string.char` from a table or a variable, as in `string.char(table.unpack(t))`, or through an alias in an enclosing function under another name, two numbers per call;
- what the script sends to a declared host, such as login data that a service forwards to someone else;
- a license restriction phrased in words that the check does not list, inside a name or year of the template;
- a change to `tools/` or `.github/` in the same pull request, which changes what the job `checks` reports. The job `maintainer sign-off` runs the tools of `main`, and `CODEOWNERS` makes the maintainer review those files.

The maintainer reads every change for these cases.

## Signing

The workflow `sign` runs on each push to `main` that changes what the app downloads. It waits until a maintainer approves the run in the environment `catalog-signing`. The index then gets the next version number, and the run pushes it with its signature to `gh-pages` and deploys that tree to GitHub Pages. Only the job that pushes holds a write token, and only the job that deploys may write to Pages. The run signs only the newest commit of `main`, never a lower index version than the published one, and never a lower package version than the published one, so a rerun of an old run cannot bring back old packages. A published version of a package never changes. A changed file needs a higher version in the manifest, and the checks fail without one. [Set up the signing key](docs/set-up-signing.md) describes the environment and the key rotation.

## States of a package

`status.json` gives a package a state other than active. The index carries the state and its note to every installed copy.

| State | When | Effect in Moneten |
| --- | --- | --- |
| `blocked` | The package has a security problem. A maintainer blocks it at once, without waiting for the author. | It stops running. |
| `withdrawn` | The service closed, or the author asked to withdraw the package. | It stops running. |
| `unmaintained` | The package fails in a way that others can reproduce, and its maintainer did not answer for 90 days. | It keeps running with the note. |

A package folder is never deleted, because only an index entry can stop an installed copy. To remove a package, mark it `withdrawn`.

Anyone may adopt an unmaintained package. Open a pull request that fixes the failure, puts your name in `maintainer` of its manifest, and removes its entry from `status.json`.
