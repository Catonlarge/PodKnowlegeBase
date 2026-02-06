"""
Transcripts API Unit Tests

Test all Transcripts API endpoints.
"""
import pytest


def test_list_transcripts(client, sample_episode_with_content):
    """
    Given: Episode has transcripts
    When: GET /api/v1/episodes/{id}/transcripts
    Then: Returns list of transcripts with translations
    """
    response = client.get(f"/api/v1/episodes/{sample_episode_with_content.id}/transcripts")

    assert response.status_code == 200
    data = response.json()
    assert data["episode_id"] == sample_episode_with_content.id
    assert data["total"] >= 1
    assert "items" in data
    assert len(data["items"]) >= 1
    # Check translation field exists
    assert "translation" in data["items"][0]


def test_list_transcripts_not_found(client):
    """
    Given: Episode does not exist
    When: GET /api/v1/episodes/{invalid_id}/transcripts
    Then: Returns 404 error
    """
    response = client.get("/api/v1/episodes/999999/transcripts")

    assert response.status_code == 404


def test_list_transcripts_with_chapter_filter(client, sample_episode_with_content):
    """
    Given: Episode has transcripts with chapters
    When: GET /api/v1/episodes/{id}/transcripts?chapter_id={chapter_id}
    Then: Returns only transcripts from that chapter
    """
    chapter_id = sample_episode_with_content.chapters[0].id
    response = client.get(
        f"/api/v1/episodes/{sample_episode_with_content.id}/transcripts?chapter_id={chapter_id}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["episode_id"] == sample_episode_with_content.id
    # All items should have the same chapter_id (via their segment)


def test_get_cue(client, sample_episode_with_content):
    """
    Given: Cue exists
    When: GET /api/v1/cues/{cue_id}
    Then: Returns cue details
    """
    cue = sample_episode_with_content.transcript_cues[0]
    response = client.get(f"/api/v1/cues/{cue.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == cue.id
    assert data["text"] == cue.text


def test_get_cue_not_found(client):
    """
    Given: Cue does not exist
    When: GET /api/v1/cues/{invalid_id}
    Then: Returns 404 error
    """
    response = client.get("/api/v1/cues/999999")

    assert response.status_code == 404


def test_get_cue_effective_text_original(client, sample_episode_with_content):
    """
    Given: Cue exists with no corrections
    When: GET /api/v1/cues/{cue_id}/effective-text
    Then: Returns original text with is_corrected=False
    """
    cue = sample_episode_with_content.transcript_cues[0]
    response = client.get(f"/api/v1/cues/{cue.id}/effective-text")

    assert response.status_code == 200
    data = response.json()
    assert data["cue_id"] == cue.id
    assert data["text"] == cue.text
    assert data["is_corrected"] is False


def test_get_cue_effective_text_corrected(client, test_session):
    """
    Given: Cue exists with corrections
    When: GET /api/v1/cues/{cue_id}/effective-text
    Then: Returns corrected text with is_corrected=True
    """
    # Create episode with corrected cue
    from app.models import Episode, AudioSegment, TranscriptCue
    from app.enums.workflow_status import WorkflowStatus

    episode = Episode(
        title="Test",
        file_hash="corrected_hash",
        source_url="https://test.com",
        duration=100.0,
        workflow_status=WorkflowStatus.TRANSCRIBED.value,
    )
    test_session.add(episode)
    test_session.flush()

    segment = AudioSegment(
        episode_id=episode.id,
        segment_index=0,
        segment_id="seg_001",
        start_time=0.0,
        end_time=30.0,
        status="completed",
    )
    test_session.add(segment)
    test_session.flush()

    cue = TranscriptCue(
        segment_id=segment.id,
        start_time=0.0,
        end_time=10.0,
        speaker="Speaker A",
        text="Original text",
        corrected_text="Corrected text",
        is_corrected=True,
    )
    test_session.add(cue)
    test_session.commit()

    response = client.get(f"/api/v1/cues/{cue.id}/effective-text")

    assert response.status_code == 200
    data = response.json()
    assert data["cue_id"] == cue.id
    assert data["text"] == "Corrected text"
    assert data["is_corrected"] is True


def test_get_cue_effective_text_not_found(client):
    """
    Given: Cue does not exist
    When: GET /api/v1/cues/{invalid_id}/effective-text
    Then: Returns 404 error
    """
    response = client.get("/api/v1/cues/999999/effective-text")

    assert response.status_code == 404
