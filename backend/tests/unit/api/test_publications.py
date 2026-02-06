"""
Publications API Unit Tests

Test all Publications API endpoints.
"""


def test_get_publication_status(client, sample_episode):
    """
    Given: Episode exists
    When: GET /api/v1/episodes/{id}/publication-status
    Then: Returns publication status with summary
    """
    response = client.get(f"/api/v1/episodes/{sample_episode.id}/publication-status")

    assert response.status_code == 200
    data = response.json()
    assert data["episode_id"] == sample_episode.id
    assert "records" in data
    assert "summary" in data
    assert "total" in data["summary"]
    assert "success" in data["summary"]
    assert "failed" in data["summary"]
    assert "pending" in data["summary"]


def test_get_publication_status_not_found(client):
    """
    Given: Episode does not exist
    When: GET /api/v1/episodes/{invalid_id}/publication-status
    Then: Returns 404 error
    """
    response = client.get("/api/v1/episodes/999999/publication-status")

    assert response.status_code == 404


def test_get_publication_status_with_records(client, test_session):
    """
    Given: Episode has publication records
    When: GET /api/v1/episodes/{id}/publication-status
    Then: Returns all records with correct summary
    """
    from app.models import Episode, PublicationRecord

    episode = Episode(
        title="Test",
        file_hash="pub_hash",
        source_url="https://test.com",
        duration=100.0,
        workflow_status=6,
    )
    test_session.add(episode)
    test_session.flush()

    # Create publication records
    records = [
        PublicationRecord(
            episode_id=episode.id,
            platform="notion",
            status="success",
        ),
        PublicationRecord(
            episode_id=episode.id,
            platform="feishu",
            status="failed",
            error_message="Test error",
        ),
        PublicationRecord(
            episode_id=episode.id,
            platform="ima",
            status="pending",
        ),
    ]
    for record in records:
        test_session.add(record)
    test_session.commit()

    response = client.get(f"/api/v1/episodes/{episode.id}/publication-status")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total"] == 3
    assert data["summary"]["success"] == 1
    assert data["summary"]["failed"] == 1
    assert data["summary"]["pending"] == 1
    assert len(data["records"]) == 3


def test_get_publication_record(client, test_session):
    """
    Given: Publication record exists
    When: GET /api/v1/publications/{id}
    Then: Returns record details
    """
    from app.models import Episode, PublicationRecord

    episode = Episode(
        title="Test",
        file_hash="record_hash",
        source_url="https://test.com",
        duration=100.0,
        workflow_status=6,
    )
    test_session.add(episode)
    test_session.flush()

    record = PublicationRecord(
        episode_id=episode.id,
        platform="notion",
        status="pending",
    )
    test_session.add(record)
    test_session.commit()

    response = client.get(f"/api/v1/publications/{record.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == record.id
    assert data["platform"] == "notion"


def test_get_publication_record_not_found(client):
    """
    Given: Publication record does not exist
    When: GET /api/v1/publications/{invalid_id}
    Then: Returns 404 error
    """
    response = client.get("/api/v1/publications/999999")

    assert response.status_code == 404


def test_retry_publication_success(client, test_session):
    """
    Given: Failed publication record exists
    When: POST /api/v1/publications/{id}/retry
    Then: Returns pending status
    """
    from app.models import Episode, PublicationRecord

    episode = Episode(
        title="Test",
        file_hash="retry_hash",
        source_url="https://test.com",
        duration=100.0,
        workflow_status=6,
    )
    test_session.add(episode)
    test_session.flush()

    record = PublicationRecord(
        episode_id=episode.id,
        platform="notion",
        status="failed",
        error_message="Test error",
    )
    test_session.add(record)
    test_session.commit()

    response = client.post(f"/api/v1/publications/{record.id}/retry")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == record.id
    assert data["status"] == "pending"
    assert "scheduled" in data["message"].lower()


def test_retry_publication_already_succeeded(client, test_session):
    """
    Given: Publication record already succeeded
    When: POST /api/v1/publications/{id}/retry
    Then: Returns message indicating no need to retry
    """
    from app.models import Episode, PublicationRecord

    episode = Episode(
        title="Test",
        file_hash="success_hash",
        source_url="https://test.com",
        duration=100.0,
        workflow_status=6,
    )
    test_session.add(episode)
    test_session.flush()

    record = PublicationRecord(
        episode_id=episode.id,
        platform="notion",
        status="success",
    )
    test_session.add(record)
    test_session.commit()

    response = client.post(f"/api/v1/publications/{record.id}/retry")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "no need to retry" in data["message"].lower()


def test_retry_publication_not_found(client):
    """
    Given: Publication record does not exist
    When: POST /api/v1/publications/{invalid_id}/retry
    Then: Returns 404 error
    """
    response = client.post("/api/v1/publications/999999/retry")

    assert response.status_code == 404
