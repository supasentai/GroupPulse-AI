from src.pipeline import build_account_features, classify_with_rules, demo_activities, load_payload


def test_demo_features_and_labels():
    activities = demo_activities()
    features = build_account_features(activities, anonymize=False)
    result = classify_with_rules(features)
    assert len(result) == 4
    assert "potential_customer" in set(result["label"])
    assert "advisor_or_seller" in set(result["label"])
    assert "real_customer" in set(result["label"])


def test_flat_json_is_supported():
    raw = b'[{"activity_id":"1","account_id":"u1","activity_type":"comment","content":"Cho hoi gia", "post_id":"p1"}]'
    activities = load_payload(raw, "activities.json")
    assert len(activities) == 1
    assert activities[0].activity_type == "comment"
    assert activities[0].account_id == "u1"


def test_nested_author_is_supported():
    raw = b'{"posts":[{"id":"p1","from":{"id":"u2","name":"Member"},"message":"Hello"}]}'
    activities = load_payload(raw, "nested.json")
    assert activities[0].account_id == "u2"
    assert activities[0].account_name == "Member"
