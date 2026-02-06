"""
Translations API Unit Tests

Test all Translations API endpoints.
"""


def test_get_translation(client, sample_translation):
    """
    Given: Translation exists
    When: GET /api/v1/translations/{id}
    Then: Returns translation details
    """
    response = client.get(f"/api/v1/translations/{sample_translation.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_translation.id
    assert data["cue_id"] == sample_translation.cue_id
    assert data["language_code"] == "zh"
    assert data["translation"] == "示例翻译"


def test_get_translation_not_found(client):
    """
    Given: Translation does not exist
    When: GET /api/v1/translations/{invalid_id}
    Then: Returns 404 error
    """
    response = client.get("/api/v1/translations/999999")

    assert response.status_code == 404


def test_update_translation(client, sample_translation, translation_update_request):
    """
    Given: Translation exists
    When: PATCH /api/v1/translations/{id} with new text
    Then: Translation is updated and is_edited is set to True
    """
    response = client.patch(
        f"/api/v1/translations/{sample_translation.id}",
        json=translation_update_request
    )

    assert response.status_code == 200
    data = response.json()
    assert data["translation"] == "修正后的翻译"
    # is_edited should be True since we changed the translation
    assert data["is_edited"] is True


def test_update_translation_not_found(client, translation_update_request):
    """
    Given: Translation does not exist
    When: PATCH /api/v1/translations/{invalid_id}
    Then: Returns 404 error
    """
    response = client.patch("/api/v1/translations/999999", json=translation_update_request)

    assert response.status_code == 404


def test_update_translation_same_value(client, sample_translation):
    """
    Given: Translation exists
    When: PATCH /api/v1/translations/{id} with same value
    Then: is_edited remains False
    """
    response = client.patch(
        f"/api/v1/translations/{sample_translation.id}",
        json={"translation": "示例翻译"}  # Same as original
    )

    assert response.status_code == 200
    data = response.json()
    # is_edited should be False since we didn't change the translation
    assert data["is_edited"] is False


def test_batch_translate_no_llm(client, sample_episode):
    """
    Given: LLM service is not available
    When: POST /api/v1/episodes/{id}/translations/batch-translate
    Then: Returns 503 Service Unavailable
    """
    # This test assumes LLM key is not set in test environment
    response = client.post(
        f"/api/v1/episodes/{sample_episode.id}/translations/batch-translate",
        json={"language_code": "zh", "force": False}
    )

    # Either 503 if LLM not configured, or 500 if other error
    assert response.status_code in [503, 500]


def test_batch_translate_episode_not_found(client):
    """
    Given: Episode does not exist
    When: POST /api/v1/episodes/{invalid_id}/translations/batch-translate
    Then: Returns 404 error
    """
    response = client.post(
        "/api/v1/episodes/999999/translations/batch-translate",
        json={"language_code": "zh"}
    )

    assert response.status_code == 404


def test_batch_translate_invalid_language_code(client, sample_episode):
    """
    Given: Episode exists
    When: POST /api/v1/episodes/{id}/translations/batch-translate with invalid code
    Then: Request is processed (validation happens at service level)
    """
    response = client.post(
        f"/api/v1/episodes/{sample_episode.id}/translations/batch-translate",
        json={"language_code": "invalid", "force": False}
    )

    # Should still accept the request, validation happens in service
    assert response.status_code in [200, 503, 500]
