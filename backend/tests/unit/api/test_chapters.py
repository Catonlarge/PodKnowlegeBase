"""
Chapters API Unit Tests

Test all Chapters API endpoints.
"""


def test_list_chapters(client, sample_episode_with_content):
    """
    Given: Episode has chapters
    When: GET /api/v1/episodes/{id}/chapters
    Then: Returns list of chapters
    """
    response = client.get(f"/api/v1/episodes/{sample_episode_with_content.id}/chapters")

    assert response.status_code == 200
    data = response.json()
    assert data["episode_id"] == sample_episode_with_content.id
    assert data["total"] >= 1
    assert "items" in data
    assert len(data["items"]) >= 1
    # Verify chapter is sorted by chapter_index
    indices = [item["chapter_index"] for item in data["items"]]
    assert indices == sorted(indices)


def test_list_chapters_not_found(client):
    """
    Given: Episode does not exist
    When: GET /api/v1/episodes/{invalid_id}/chapters
    Then: Returns 404 error
    """
    response = client.get("/api/v1/episodes/999999/chapters")

    assert response.status_code == 404


def test_get_chapter(client, sample_episode_with_content):
    """
    Given: Chapter exists
    When: GET /api/v1/chapters/{id}
    Then: Returns chapter details with cues_count
    """
    chapter = sample_episode_with_content.chapters[0]
    response = client.get(f"/api/v1/chapters/{chapter.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == chapter.id
    assert data["title"] == chapter.title
    assert "cues_count" in data
    assert "duration" in data


def test_get_chapter_not_found(client):
    """
    Given: Chapter does not exist
    When: GET /api/v1/chapters/{invalid_id}
    Then: Returns 404 error
    """
    response = client.get("/api/v1/chapters/999999")

    assert response.status_code == 404


def test_get_chapter_cues(client, sample_episode_with_content):
    """
    Given: Chapter has cues
    When: GET /api/v1/chapters/{id}/cues
    Then: Returns cues belonging to the chapter
    """
    chapter = sample_episode_with_content.chapters[0]
    response = client.get(f"/api/v1/chapters/{chapter.id}/cues")

    assert response.status_code == 200
    data = response.json()
    assert data["chapter_id"] == chapter.id
    assert "total" in data
    assert "items" in data
    # Verify cues are sorted by start_time
    start_times = [item["start_time"] for item in data["items"]]
    assert start_times == sorted(start_times)


def test_get_chapter_cues_not_found(client):
    """
    Given: Chapter does not exist
    When: GET /api/v1/chapters/{invalid_id}/cues
    Then: Returns 404 error
    """
    response = client.get("/api/v1/chapters/999999/cues")

    assert response.status_code == 404


def test_chapter_duration_calculation(client, sample_episode_with_content):
    """
    Given: Chapter has start_time and end_time
    When: GET /api/v1/chapters/{id}
    Then: duration is correctly calculated
    """
    chapter = sample_episode_with_content.chapters[0]
    response = client.get(f"/api/v1/chapters/{chapter.id}")

    assert response.status_code == 200
    data = response.json()
    expected_duration = chapter.end_time - chapter.start_time
    assert data["duration"] == expected_duration
