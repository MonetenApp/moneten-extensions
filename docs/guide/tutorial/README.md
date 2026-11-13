# Sample Fake Bank

This package is the finished result of the [tutorial](../tutorial.md). It is not in the catalog.

The script reads the card transactions of the fake bank of [SampleAPIs](https://github.com/jermbo/SampleAPIs) from `https://api.sampleapis.com/fakebank/accounts`. The API needs no login and no key. All its names and amounts are made up.

The script asks for one login field, "Any name", because Moneten asks for at least one field. The script does not use the value.

The recording in `recording/` holds one request and its answer. `ext test` replays it without a network.
