from instagram_content_priority import InstagramContentPriority


def test_priority_classification():
    p = InstagramContentPriority(min_score_threshold=35)

    assert p.classify(95) == "CRITICAL"
    assert p.classify(80) == "HIGH"
    assert p.classify(60) == "NORMAL"
    assert p.classify(40) == "LOW"
    assert p.classify(20) == "REJECT"


def test_priority_should_queue():
    p = InstagramContentPriority(min_score_threshold=35)

    assert p.should_queue(90) is True
    assert p.should_queue(35) is True
    assert p.should_queue(20) is False
