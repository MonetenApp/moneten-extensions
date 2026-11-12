# Set up the signing key

The workflow `sign` signs the catalog index and publishes it to `https://extensions.monetenapp.com`. It needs a key pair, a protected environment, and GitHub Pages. A maintainer with admin rights on `MonetenApp/moneten-extensions` does these steps once. GitHub does not let a workflow token set environment protection rules, so no automation does them.

## Make the two key pairs

Use OpenSSL 3 or later. `openssl version` shows the version.

1. In a folder outside every git repository, run:

	```sh
	openssl genpkey -algorithm ed25519 -out current.pem
	openssl genpkey -algorithm ed25519 -out next.pem
	openssl pkey -in current.pem -pubout -out current.pub
	openssl pkey -in next.pem -pubout -out next.pub
	```

2. Store `current.pem` and `next.pem` in your password manager or on an encrypted volume. Never commit them.
3. Open a pull request that adds `current.pub` and `next.pub` to `keys/`. Moneten copies these two files into the app.

## Create the environment

1. Open the repository on GitHub and click **Settings**.
2. In the sidebar, click **Environments**, then **New environment**.
3. Type `catalog-signing` as the name and click **Configure environment**.
4. Under **Deployment protection rules**, select **Required reviewers**. Add yourself and click **Save protection rules**. Leave **Prevent self-review** cleared, because the merge that starts a signing run is usually your own.
5. Under **Deployment branches and tags**, choose **Selected branches and tags**. Click **Add deployment branch or tag rule**, type `main`, and click **Add rule**.
6. Under **Environment secrets**, click **Add environment secret**.
7. Type `INDEX_SIGNING_KEY` as the name. As the value, paste the whole content of `current.pem`, including the lines `-----BEGIN PRIVATE KEY-----` and `-----END PRIVATE KEY-----`. On a Mac, `pbcopy < current.pem` copies it. Click **Add secret**.

## Approve the first signing run

Each push to `main` that changes a package, `status.json`, `keys/`, `schema/`, or the signing tools starts the workflow `sign`. The run waits for your approval.

1. Click **Actions**, then the waiting run of **sign**.
2. Click **Review deployments**, select **catalog-signing**, and click **Approve and deploy**.

The run checks every package again, builds `index.json`, signs it, checks the signature against `keys/`, and pushes the site to the branch `gh-pages`. If the secret matches neither `keys/current.pub` nor `keys/next.pub`, or if the published index has no valid signature by one of them, the run fails and publishes nothing.

## Serve the site from extensions.monetenapp.com

Do these steps after the first signing run, because the branch `gh-pages` exists only then.

1. At your DNS provider, add the record `extensions` of type `CNAME` with the value `monetenapp.github.io`.
2. In **Settings**, click **Pages**.
3. Under **Build and deployment**, set **Source** to **Deploy from a branch**. Choose the branch `gh-pages` and the folder `/ (root)`, and click **Save**.
4. Under **Custom domain**, type `extensions.monetenapp.com` and click **Save**.
5. When the DNS check passes, select **Enforce HTTPS**.

`curl -s https://extensions.monetenapp.com/index.json` then shows the signed index.

## Protect main

The checks only help when a pull request cannot skip them.

1. In **Settings**, click **Branches**, then **Add classic branch protection rule**. Type `main` as the branch name pattern.
2. Select **Require a pull request before merging**, **Require approvals** with 1, and **Require review from Code Owners**.
3. Select **Dismiss stale pull request approvals when new commits are pushed** and **Require approval of the most recent reviewable push**. An approval then covers only the commits that the maintainer read.
4. Select **Require status checks to pass before merging** and add `checks` and `maintainer sign-off`. Add `ext test` when `tools/ext.lock` pins a commit. Until then the job is skipped, and GitHub counts a skipped required check as passed.
5. Click **Create**.

GitHub does not count the approval of a pull request's author. While you are the only maintainer, leave **Do not allow bypassing the above settings** cleared, so that you can merge your own pull requests as an admin.

## Protect gh-pages

The app trusts only the signature, but a rewritten `gh-pages` could serve an older signed index or delete the site.

1. In **Settings**, click **Branches**, then **Add classic branch protection rule**. Type `gh-pages` as the branch name pattern.
2. Leave **Allow force pushes** and **Allow deletions** cleared. Select nothing else, because the workflow `sign` must push new commits.
3. Click **Create**.

## Verify the Pages domain

A verified domain stops another GitHub account from serving a site at `extensions.monetenapp.com` when the Pages setting is off.

1. Open the settings of the organization `MonetenApp`, and click **Pages** under **Code, planning, and automation**.
2. Click **Add a domain**, type `monetenapp.com`, and click **Add domain**.
3. At your DNS provider, add the `TXT` record that GitHub shows. Click **Verify**.

## Move to the next key

Each signing run first checks that the published `index.json` is signed by `keys/current.pub` or `keys/next.pub`. So the published index must carry the signature of the next key before `keys/` drops the current key.

1. Make a new key pair as in the first section. It becomes the new next key.
2. In the environment `catalog-signing`, replace the secret `INDEX_SIGNING_KEY` with the content of `next.pem`.
3. Click **Actions**, then **sign**, then **Run workflow** on `main`. Approve the run. It publishes the index signed with the next key.
4. In a pull request, replace `keys/current.pub` with the old `keys/next.pub`, and `keys/next.pub` with the new public key.
5. Merge the pull request and approve the signing run.

Apps that ship the old pair accept the index after step 3, because it is signed with their next key. A Moneten release then ships the new pair.
