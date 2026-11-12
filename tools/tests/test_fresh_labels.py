from fresh_labels import split_labels

PUSHED = "2026-11-12T14:00:00Z"


def event(kind, name, at):
    return {"event": kind, "label": {"name": name}, "created_at": at}


def test_label_set_after_the_newest_push_counts():
    events = [event("labeled", "hosts-approved", "2026-11-12T14:05:00Z")]
    assert split_labels(events, PUSHED) == (["hosts-approved"], [])


def test_label_set_before_the_newest_push_is_stale():
    events = [event("labeled", "hosts-approved", "2026-11-12T13:55:00Z"), event("labeled", "io-acknowledged", "2026-11-12T14:01:00Z")]
    assert split_labels(events, PUSHED) == (["io-acknowledged"], ["hosts-approved"])


def test_label_set_again_after_the_push_counts_again():
    events = [
        event("labeled", "hosts-approved", "2026-11-12T13:55:00Z"),
        event("unlabeled", "hosts-approved", "2026-11-12T14:02:00Z"),
        event("labeled", "hosts-approved", "2026-11-12T14:03:00Z"),
    ]
    assert split_labels(events, PUSHED) == (["hosts-approved"], [])


def test_removed_label_counts_neither_way():
    events = [event("labeled", "hosts-approved", "2026-11-12T14:01:00Z"), event("unlabeled", "hosts-approved", "2026-11-12T14:02:00Z")]
    assert split_labels(events, PUSHED) == ([], [])
