"""
Marketing API Unit Tests

Test all Marketing API endpoints.
"""


def test_list_marketing_posts(client, sample_episode):
    """
    Given: Episode exists
    When: GET /api/v1/episodes/{id}/marketing-posts
    Then: Returns list of marketing posts (empty if none)
    """
    response = client.get(f"/api/v1/episodes/{sample_episode.id}/marketing-posts")

    assert response.status_code == 200
    data = response.json()
    assert data["episode_id"] == sample_episode.id
    assert "total" in data
    assert "items" in data


def test_list_marketing_posts_not_found(client):
    """
    Given: Episode does not exist
    When: GET /api/v1/episodes/{invalid_id}/marketing-posts
    Then: Returns 404 error
    """
    response = client.get("/api/v1/episodes/999999/marketing-posts")

    assert response.status_code == 404


def test_list_marketing_posts_with_filters(client, test_session):
    """
    Given: Episode has marketing posts
    When: GET /api/v1/episodes/{id}/marketing-posts?platform=xhs&angle_tag=xxx
    Then: Returns filtered list
    """
    from app.models import Episode, MarketingPost

    episode = Episode(
        title="Test",
        file_hash="marketing_hash",
        source_url="https://test.com",
        duration=100.0,
        workflow_status=6,
    )
    test_session.add(episode)
    test_session.flush()

    # Create some posts
    for i in range(3):
        post = MarketingPost(
            episode_id=episode.id,
            platform="xhs" if i % 2 == 0 else "twitter",
            angle_tag=f"angle_{i}",
            title=f"Post {i}",
            content=f"Content {i}",
        )
        test_session.add(post)
    test_session.commit()

    # Filter by platform
    response = client.get(
        f"/api/v1/episodes/{episode.id}/marketing-posts?platform=xhs"
    )

    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["platform"] == "xhs"


def test_generate_marketing_posts_no_llm(client, sample_episode):
    """
    Given: LLM service is not available
    When: POST /api/v1/episodes/{id}/marketing-posts/generate
    Then: Returns 503 Service Unavailable
    """
    response = client.post(
        f"/api/v1/episodes/{sample_episode.id}/marketing-posts/generate",
        json={"platform": "xhs", "angles": None}
    )

    assert response.status_code in [503, 500]


def test_generate_marketing_posts_not_found(client):
    """
    Given: Episode does not exist
    When: POST /api/v1/episodes/{invalid_id}/marketing-posts/generate
    Then: Returns 404 error
    """
    response = client.post(
        "/api/v1/episodes/999999/marketing-posts/generate",
        json={"platform": "xhs"}
    )

    assert response.status_code == 404


def test_get_marketing_post(client, test_session):
    """
    Given: Marketing post exists
    When: GET /api/v1/marketing-posts/{id}
    Then: Returns post details
    """
    from app.models import Episode, MarketingPost

    episode = Episode(
        title="Test",
        file_hash="post_hash",
        source_url="https://test.com",
        duration=100.0,
        workflow_status=6,
    )
    test_session.add(episode)
    test_session.flush()

    post = MarketingPost(
        episode_id=episode.id,
        platform="xhs",
        angle_tag="test_angle",
        title="Test Post",
        content="Test content",
    )
    test_session.add(post)
    test_session.commit()

    response = client.get(f"/api/v1/marketing-posts/{post.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == post.id
    assert data["platform"] == "xhs"
    assert data["angle_tag"] == "test_angle"


def test_get_marketing_post_not_found(client):
    """
    Given: Marketing post does not exist
    When: GET /api/v1/marketing-posts/{invalid_id}
    Then: Returns 404 error
    """
    response = client.get("/api/v1/marketing-posts/999999")

    assert response.status_code == 404
