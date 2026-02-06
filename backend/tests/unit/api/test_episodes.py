"""
Episodes API Unit Tests

Test all Episodes API endpoints.
"""
from pytest import Session


def test_create_episode(client, episode_create_request):
    """
    Given: Valid episode create request
    When: POST /api/v1/episodes
    Then: Episode is created with correct data
    """
    response = client.post("/api/v1/episodes", json=episode_create_request)

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Episode Title"
    assert data["source_url"] == episode_create_request["url"]
    assert data["workflow_status"] == 0  # INIT
    assert "id" in data


def test_create_episode_duplicate_url(client, episode_create_request, sample_episode):
    """
    Given: Episode with URL already exists
    When: POST /api/v1/episodes with same URL
    Then: Returns existing episode
    """
    response = client.post("/api/v1/episodes", json=episode_create_request)

    assert response.status_code == 200  # Not 201, because episode exists
    data = response.json()
    assert data["id"] == sample_episode.id


def test_create_episode_invalid_url(client):
    """
    Given: Invalid URL (empty)
    When: POST /api/v1/episodes
    Then: Returns 422 validation error
    """
    response = client.post("/api/v1/episodes", json={"url": ""})

    assert response.status_code == 422


def test_list_episodes(client, sample_episode):
    """
    Given: Database has episodes
    When: GET /api/v1/episodes
    Then: Returns paginated list of episodes
    """
    response = client.get("/api/v1/episodes")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    assert "items" in data
    assert len(data["items"]) >= 1


def test_list_episodes_with_status_filter(client, sample_episode):
    """
    Given: Database has episodes with different statuses
    When: GET /api/v1/episodes?status=6
    Then: Returns only episodes with that status
    """
    # Filter by READY_FOR_REVIEW status (6)
    response = client.get("/api/v1/episodes?status=6")

    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["workflow_status"] == 6


def test_list_episodes_with_invalid_status(client):
    """
    Given: Invalid status value
    When: GET /api/v1/episodes?status=999
    Then: Returns 400 error
    """
    response = client.get("/api/v1/episodes?status=999")

    assert response.status_code == 400


def test_list_episodes_with_pagination(client, test_session):
    """
    Given: Database has multiple episodes
    When: GET /api/v1/episodes?page=1&limit=10
    Then: Returns paginated results
    """
    # Create additional episodes
    for i in range(5):
        episode = Session(
            title=f"Episode {i}",
            file_hash=f"hash_{i}",
            source_url=f"https://test.com/{i}",
            duration=100.0,
            workflow_status=0,
        )
        test_session.add(episode)
    test_session.commit()

    response = client.get("/api/v1/episodes?page=1&limit=3")

    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["limit"] == 3
    assert len(data["items"]) <= 3
    assert data["pages"] > 0


def test_get_episode_detail(client, sample_episode):
    """
    Given: Episode exists
    When: GET /api/v1/episodes/{id}
    Then: Returns episode detail with statistics
    """
    response = client.get(f"/api/v1/episodes/{sample_episode.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_episode.id
    assert data["title"] == sample_episode.title
    assert "segments_count" in data
    assert "cues_count" in data
    assert "chapters_count" in data


def test_get_episode_not_found(client):
    """
    Given: Episode does not exist
    When: GET /api/v1/episodes/{invalid_id}
    Then: Returns 404 error
    """
    response = client.get("/api/v1/episodes/999999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_update_episode(client, sample_episode, episode_update_request):
    """
    Given: Episode exists
    When: PATCH /api/v1/episodes/{id} with update data
    Then: Episode is updated
    """
    response = client.patch(
        f"/api/v1/episodes/{sample_episode.id}",
        json=episode_update_request
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["ai_summary"] == "Updated summary"


def test_update_episode_not_found(client, episode_update_request):
    """
    Given: Episode does not exist
    When: PATCH /api/v1/episodes/{invalid_id}
    Then: Returns 404 error
    """
    response = client.patch("/api/v1/episodes/999999", json=episode_update_request)

    assert response.status_code == 404


def test_delete_episode(client, test_session):
    """
    Given: Episode exists
    When: DELETE /api/v1/episodes/{id}
    Then: Episode is deleted
    """
    # Create a temporary episode
    episode = Session(
        title="To Delete",
        file_hash="delete_hash",
        source_url="https://delete.com",
        duration=100.0,
        workflow_status=0,
    )
    test_session.add(episode)
    test_session.commit()
    episode_id = episode.id

    response = client.delete(f"/api/v1/episodes/{episode_id}")

    assert response.status_code == 204
    assert response.content == b""


def test_delete_episode_not_found(client):
    """
    Given: Episode does not exist
    When: DELETE /api/v1/episodes/{invalid_id}
    Then: Returns 404 error
    """
    response = client.delete("/api/v1/episodes/999999")

    assert response.status_code == 404


def test_run_episode_workflow(client, sample_episode):
    """
    Given: Episode exists
    When: POST /api/v1/episodes/{id}/run
    Then: Workflow is triggered (returns immediately)
    """
    response = client.post(
        f"/api/v1/episodes/{sample_episode.id}/run",
        json={"force_restart": False}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_episode.id


def test_run_episode_workflow_not_found(client):
    """
    Given: Episode does not exist
    When: POST /api/v1/episodes/{invalid_id}/run
    Then: Returns 404 error
    """
    response = client.post("/api/v1/episodes/999999/run")

    assert response.status_code == 404


def test_publish_episode(client, sample_episode):
    """
    Given: Episode in READY_FOR_REVIEW status
    When: POST /api/v1/episodes/{id}/publish
    Then: Publishing is triggered
    """
    response = client.post(
        f"/api/v1/episodes/{sample_episode.id}/publish",
        json={"generate_marketing": True}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_episode.id


def test_publish_episode_invalid_status(client, test_session):
    """
    Given: Episode not in READY_FOR_REVIEW status
    When: POST /api/v1/episodes/{id}/publish
    Then: Returns 400 error
    """
    # Create episode in INIT status
    episode = Session(
        title="Init Episode",
        file_hash="init_hash",
        source_url="https://init.com",
        duration=100.0,
        workflow_status=0,  # INIT
    )
    test_session.add(episode)
    test_session.commit()

    response = client.post(f"/api/v1/episodes/{episode.id}/publish")

    assert response.status_code == 400
    assert "READY_FOR_REVIEW" in response.json()["detail"]
