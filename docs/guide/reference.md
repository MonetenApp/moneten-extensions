# Reference: differences from the Web Banking API

Moneten gives extensions the [Web Banking API of MoneyMoney](https://moneymoney.app/api/webbanking/). This page does not repeat that API. It lists each point where Moneten is different from the published API, or where the published API says nothing.

Each entry tells what the published API says and what Moneten does. A script that obeys this page runs in Moneten and in MoneyMoney.

- [Lua runtime](#lua-runtime)
- [Names that the API page does not document](#names-that-the-api-page-does-not-document)
- [Product name and API version](#product-name-and-api-version)
- [Manifest and login fields](#manifest-and-login-fields)
- [Packages](#packages)
- [Hosts and redirects](#hosts-and-redirects)
- [Browser login](#browser-login)
- [Captcha](#captcha)
- [Decoupled approval](#decoupled-approval)
- [Return values of a request](#return-values-of-a-request)
- [HTTP errors and the Accept header](#http-errors-and-the-accept-header)
- [Limits of a session](#limits-of-a-session)
- [No payments](#no-payments)

## Lua runtime

The published API does not list the Lua libraries. Its review checklist forbids `io` and some `os` functions. Signed MoneyMoney extensions appear to get an `io` table without `open`.

Moneten runs Lua 5.4 with the libraries `string`, `table`, `math`, `utf8`, and `coroutine`, and with these changes:

- `io` is a table without functions. `io.open` is `nil`. A script that does `local open = io.open` loads without an error.
- `os` has only `time`, `date`, `clock`, and `difftime`.
- `debug`, `package`, `load`, `loadstring`, `dofile`, `loadfile`, `require`, and `string.dump` are absent.

A read of a removed name gives `nil`. A call of a removed name stops the script with an error. The error names the function and the line, for example `Demo.lua:7: require is not available`.

Use a test such as `if io ~= nil and io.open ~= nil then` before you use a file. In Moneten the test is always false.

## Names that the API page does not document

Some signed MoneyMoney extensions use names that the API page does not document. Moneten gives these names:

| Name | What it does in Moneten |
| --- | --- |
| `MM.derdecode(data)` | Returns the DER elements at the top level of `data`, each as `{tag, content}`, with the tag byte as a number. |
| `MM.base64urldecode(text)` | Decodes Base64url, with or without padding. |
| `connection.redirects` | When it is `false`, the connection does not follow redirects. |
| The fifth value of `connection:get` | The headers of the answer, as for `connection:request`. |
| `elements:html()` | Returns the markup of each element in turn. |
| `JSON(json):array()` | Returns the same as `JSON(json):dictionary()`. |

A call of any other function that Moneten does not give stops the script. The error names the function and the line. A read of such a name gives `nil`, so a type check such as `if type(MM.something) == "function"` works. Moneten never ignores the call, because a call that does nothing can give wrong data. If your script needs a name that is not on this list, open an issue in [MonetenApp/Moneten](https://github.com/MonetenApp/Moneten/issues).

## Product name and API version

The published API has `MM.productName` with the value "MoneyMoney". In Moneten, `MM.productName` is "Moneten".

Moneten adds `MM.apiVersion`, a number. It is 1 now. A manifest gives the lowest API version that the extension needs in `apiVersion`. A Moneten with a lower API version does not load the extension. It tells the user to update the app. In MoneyMoney, `MM.apiVersion` is `nil`.

## Manifest and login fields

MoneyMoney has no manifest. It keeps the labels of the login fields of each service in its own database. A new service gets the fields "Username" and "Password".

A catalog package of Moneten must have a `manifest.json`. It lists the hosts and the services with the labels of their login fields. It also gives the kinds of data, the lowest API version, the license, and the maintainer. [Manifest](manifest.md) describes each field.

A user can install a single file by hand. A manifest with the same base name can go next to it, such as `Demo.json` next to `Demo.lua`. Without a manifest, Moneten shows "Username" and "Password" and asks the user before each new host.

## Packages

A MoneyMoney extension is one `.lua` file.

A Moneten package is a folder with `manifest.json`, one or more Lua files, a `README.md`, a `LICENSE`, and a recording. `files` in the manifest lists the Lua files in load order. All files run in the same Lua state. A global of the first file is visible in the second file. Moneten installs, updates, and removes the folder as one unit. A file name holds only letters, digits, underscores, and hyphens before `.lua`.

## Hosts and redirects

The published API does not limit the hosts that a script contacts.

Moneten lets a catalog package contact only the hosts in `hosts` of its manifest:

- The match is exact. `api.bank.example` does not let the script contact `www.bank.example` or `bank.example`. There are no wildcards.
- The address must use `https`, port 443 or no port, and a host name. Moneten refuses `http`, an IP address, `localhost`, and a name without a dot. It also refuses a user name or a password in the address, and a percent sign in the host.
- Moneten checks the target of each redirect with the same rules before it follows it. It follows at most 10 redirects for one request.
- A redirect to another host takes along only the headers `Accept`, `Accept-Language`, and `User-Agent`, and no body. A header such as `Authorization`, `Cookie`, or `X-API-Key` does not go to the other host. Moneten sends the cookies of the other host from its own cookie store.
- A redirect with status 303 becomes a `GET` without a body. A redirect with status 301 or 302 after a `POST` also becomes a `GET` without a body.

Moneten does not send a refused request. The script stops with an error that names the host, for example `Demo may not contact tracker.example, because its manifest does not list that host.`

A script cannot set a header that starts with `Proxy-`. It also cannot set these headers: `Host`, `Connection`, `Content-Length`, `Transfer-Encoding`, `Keep-Alive`, `Upgrade`, `TE`, and `Trailer`. A header name has only the characters of an HTTP token. A header value cannot hold a line break or a null character.

An extension that a user installs as a file without a manifest gets no host list. Moneten asks the user before the first contact with each host, also before a redirect to a new host. In an automatic refresh, Moneten sends nothing to a new host, stops the session, and waits for the user.

## Browser login

The published API opens a URL in `challenge` in a browser window when the vendor enabled the host. It names the end of the login a "vereinbarte Weiterleitungs-URL" and does not publish that address.

Moneten opens a browser window only for a host that the extension can contact. For a catalog package, the login host must be in `hosts` of the manifest. This is also true when the script sends no request to that host.

Moneten adds a random `state` parameter to the URL when the challenge table and the URL have no `state`. MoneyMoney does the same.

When the website redirects to one of these addresses, Moneten closes the window and does not contact the address:

- `https://service.moneymoney-app.com/1/redirect`
- `moneymoney-app://oauth`
- `moneten://oauth`

Moneten gives the script the first of these parameters in `credentials[1]`: `code`, `access_token`, `auth_code`, `authorization_code`, and `tokenid`. When the address has none of them, the session stops with an error. If your service uses another parameter name, open an issue in [MonetenApp/Moneten](https://github.com/MonetenApp/Moneten/issues).

## Captcha

The published API names the captcha services and lists their script addresses.

Moneten shows a captcha only when `challenge` is exactly one of these script addresses, with the `sitekey` in the query:

| Service | Script address |
| --- | --- |
| Google reCAPTCHA | `https://www.google.com/recaptcha/api.js`, `https://www.google.com/recaptcha/enterprise.js`, or the same paths on `www.recaptcha.net` |
| hCaptcha | `https://js.hcaptcha.com/1/api.js` |
| FriendlyCaptcha | `https://cdn.jsdelivr.net/npm/friendly-challenge/widget.module.min.js` or `https://cdn.jsdelivr.net/npm/@friendlycaptcha/sdk/site.min.js`, each with or without `@` and a version after the package name |
| Amazon WAF | `https://<name>.token.awswaf.com/<path>/challenge.js` |

The optional `referer` parameter is the page that holds the captcha. Its host must be a host that the extension can contact. The optional `type=checkbox` shows the checkbox variant.

## Decoupled approval

The published API says that MoneyMoney decides how often and how long it asks again. It gives no numbers.

For a challenge with `poll=true` and no `label`, Moneten calls the function again every second, for at most 5 minutes. On the last call, `credentials[3]` is `false`. Do not count the calls in the script.

## Return values of a request

The published API documents three return values for `connection:get` and `connection:post`, and five for `connection:request`.

In Moneten, `connection:request`, `connection:get`, and `connection:post` all return five values: `content`, `charset`, `mimeType`, `filename`, and `headers`.

## HTTP errors and the Accept header

The published API stops the script on an HTTP error status, except when the request header `Accept` is `application/json`. It does not say how Moneten compares the header.

Moneten returns the answer of an error status to the script when any entry of the `Accept` header is `application/json`. The case of the header name and of the value has no effect. Parameters such as `; charset=utf-8` also have no effect. `application/json, text/plain, */*` also counts.

## Limits of a session

The published API gives no limits. Moneten stops a session that goes above one of these limits, with an error that names the limit:

| Limit | Value |
| --- | --- |
| Memory of the Lua state, with the bytes of the JSON, HTML, and PDF documents that the script opens | 256 MB |
| Processor time of one session | 60 seconds |
| Time without a sign of life from the script | 180 seconds |
| Longest pause of one `MM.sleep` | 300 seconds |
| Body of one answer | 32 MB |
| Bytes from `MM.random` in one call | 1 MB |
| Redirects of one request | 10 |

`MM.sleep` gives a sign of life each second, so a long pause is not silence. A request to the network ends in two minutes or less.

Moneten also applies these rules:

- It keeps the first 4 MB of the output of `print` in one session and drops the rest.
- A session runs one call of an entry point at a time. A second call while the first call runs fails with the error "Another call of this extension session is still running."
- An error message from a function of the API can quote data of the script. Moneten cuts such a message to 1,000 bytes and adds "…".

## No payments

The published API documents no payment functions. Some extensions define `SubmitPayment` or `FetchScheduledPayments`.

Moneten never calls these functions. It has no function, entry point, or session reason that sends a payment. An account from an extension is read-only in Moneten. A script can keep the functions, but they have no effect.
