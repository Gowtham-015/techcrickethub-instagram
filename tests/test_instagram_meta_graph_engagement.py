from unittest.mock import MagicMock
from instagram_client import InstagramAPIClient
from instagram_engagement import MetaGraphEngagementProvider, sync_recent_post_engagement


def test_meta_graph_engagement_provider():
    client = MagicMock(spec=InstagramAPIClient)
    client.get.side_effect = [
        {"like_count": 120, "comments_count": 15},
        {
            "data": [
                {"name": "impressions", "values": [{"value": 1500}]},
                {"name": "reach", "values": [{"value": 1200}]},
                {"name": "saved", "values": [{"value": 45}]},
                {"name": "shares", "values": [{"value": 22}]},
            ]
        },
    ]

    provider = MetaGraphEngagementProvider(client=client)
    res = provider.get_engagement_metrics("17841400000000001")

    assert res["status"] == "SUCCESS"
    assert res["media_id"] == "17841400000000001"
    assert res["likes"] == 120
    assert res["comments"] == 15
    assert res["impressions"] == 1500
    assert res["reach"] == 1200
    assert res["saved"] == 45
    assert res["shares"] == 22


def test_meta_graph_engagement_provider_pending():
    client = MagicMock(spec=InstagramAPIClient)
    client.get.side_effect = Exception("Graph API 400: Insights not ready yet")

    provider = MetaGraphEngagementProvider(client=client)
    res = provider.get_engagement_metrics("17841400000000002")

    assert res["status"] == "PENDING"
    assert res["media_id"] == "17841400000000002"
    assert res["reach"] is None
