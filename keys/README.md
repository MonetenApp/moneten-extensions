# Signing keys

This folder holds the two Ed25519 public keys of the catalog. Moneten ships copies of both and accepts an index signed with either.

| File | Key |
| --- | --- |
| `current.pub` | The key that signs every index now. Its private key is the secret `INDEX_SIGNING_KEY` of the environment `catalog-signing`. |
| `next.pub` | The key that replaces `current.pub`. Its private key stays offline with the maintainer. |

Both files are PEM public keys, as `openssl pkey -pubout` writes them. CryptoKit needs the raw 32-byte key, which is the last 32 bytes of the DER form:

```sh
openssl pkey -pubin -in keys/current.pub -outform DER | tail -c 32 > current.raw
```

The signing workflow fails until both files exist. [Set up the signing key](../docs/set-up-signing.md) says how to make them.
