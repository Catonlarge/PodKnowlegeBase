"""
Unit tests for Chapter model.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from sqlalchemy.exc import IntegrityError

from app.models.chapter import Chapter
from app.models.episode import Episode


class TestChapterCreate:
    """Test Chapter creation."""

    def test_chapter_create_minimal_fields(self, test_session):
        """Given: Database session and episode
        When: Creating Chapter with minimal fields
        Then: Chapter is created with correct defaults
        """
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(chapter)
        test_session.flush()

        assert chapter.id is not None
        assert chapter.episode_id == episode.id
        assert chapter.chapter_index == 0
        assert chapter.title == "第一章"
        assert chapter.start_time == 0.0
        assert chapter.end_time == 30.0
        assert chapter.summary is None
        assert chapter.status == "pending"  # Default value
        assert chapter.ai_model_used is None

    def test_chapter_create_full_fields(self, test_session):
        """Given: Database session and episode
        When: Creating Chapter with all fields
        Then: All field values are correctly set
        """
        episode = Episode(
            title="Test Episode",
            file_hash="xyz789",
            duration=300.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=1,
            title="第二章",
            summary="这是第二章的摘要。",
            start_time=30.0,
            end_time=60.0,
            status="completed",
            ai_model_used="gpt-4",
        )
        test_session.add(chapter)
        test_session.flush()

        assert chapter.episode_id == episode.id
        assert chapter.chapter_index == 1
        assert chapter.title == "第二章"
        assert chapter.summary == "这是第二章的摘要。"
        assert chapter.start_time == 30.0
        assert chapter.end_time == 60.0
        assert chapter.status == "completed"
        assert chapter.ai_model_used == "gpt-4"

    def test_chapter_status_default_is_pending(self, test_session):
        """Given: New Chapter
        When: Not specifying status
        Then: Defaults to 'pending'
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            start_time=0.0,
            end_time=10.0,
        )
        test_session.add(chapter)
        test_session.flush()

        assert chapter.status == "pending"


class TestChapterConstraints:
    """Test Chapter database constraints."""

    def test_chapter_episode_id_not_null_constraint(self, test_session):
        """Given: Chapter without episode_id
        When: Attempting to save
        Then: Raises IntegrityError
        """
        chapter = Chapter(
            # episode_id is missing
            chapter_index=0,
            title="第一章",
            start_time=0.0,
            end_time=10.0,
        )
        test_session.add(chapter)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_chapter_chapter_index_not_null_constraint(self, test_session):
        """Given: Chapter without chapter_index
        When: Attempting to save
        Then: Raises error
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            # chapter_index is missing
            title="第一章",
            start_time=0.0,
            end_time=10.0,
        )
        test_session.add(chapter)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_chapter_title_not_null_constraint(self, test_session):
        """Given: Chapter without title
        When: Attempting to save
        Then: Raises error
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            # title is missing
            start_time=0.0,
            end_time=10.0,
        )
        test_session.add(chapter)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_chapter_start_time_not_null_constraint(self, test_session):
        """Given: Chapter without start_time
        When: Attempting to save
        Then: Raises error
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            # start_time is missing
            end_time=10.0,
        )
        test_session.add(chapter)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_chapter_end_time_not_null_constraint(self, test_session):
        """Given: Chapter without end_time
        When: Attempting to save
        Then: Raises error
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            start_time=0.0,
            # end_time is missing
        )
        test_session.add(chapter)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_chapter_unique_constraint_episode_id_chapter_index(self, test_session):
        """Given: Episode with existing chapter at index 0
        When: Creating another chapter with same episode_id and chapter_index
        Then: Raises IntegrityError
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        # Create first chapter
        chapter1 = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(chapter1)
        test_session.flush()

        # Try to create duplicate
        chapter2 = Chapter(
            episode_id=episode.id,
            chapter_index=0,  # Same index
            title="第二章",
            start_time=30.0,
            end_time=60.0,
        )
        test_session.add(chapter2)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_chapter_different_episodes_same_index_allowed(self, test_session):
        """Given: Two different episodes
        When: Creating chapters with same chapter_index for each episode
        Then: Both chapters are created successfully
        """
        episode1 = Episode(
            title="Episode 1",
            file_hash="hash1",
            duration=100.0,
        )
        episode2 = Episode(
            title="Episode 2",
            file_hash="hash2",
            duration=100.0,
        )
        test_session.add(episode1)
        test_session.add(episode2)
        test_session.flush()

        # Both chapters can have index 0 because they belong to different episodes
        chapter1 = Chapter(
            episode_id=episode1.id,
            chapter_index=0,
            title="Episode 1 Chapter 1",
            start_time=0.0,
            end_time=30.0,
        )
        chapter2 = Chapter(
            episode_id=episode2.id,
            chapter_index=0,
            title="Episode 2 Chapter 1",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(chapter1)
        test_session.add(chapter2)
        test_session.flush()

        assert chapter1.id is not None
        assert chapter2.id is not None


class TestChapterProperties:
    """Test Chapter properties."""

    def test_chapter_duration_property(self, test_session):
        """Given: Chapter with start_time and end_time
        When: Accessing duration property
        Then: Returns correct duration (end_time - start_time)
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            start_time=10.5,
            end_time=45.5,
        )
        test_session.add(chapter)
        test_session.flush()

        assert chapter.duration == 35.0


class TestChapterRelationships:
    """Test Chapter relationships."""

    def test_chapter_belongs_to_episode(self, test_session):
        """Given: Chapter with episode_id
        When: Accessing episode relationship
        Then: Returns correct Episode object
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(chapter)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(chapter)
        test_session.refresh(episode)

        assert chapter.episode.id == episode.id
        assert chapter.episode.title == "Test Episode"


class TestChapterRepr:
    """Test Chapter __repr__ method."""

    def test_chapter_repr_contains_id_and_title(self, test_session):
        """Given: Chapter object
        When: Calling repr()
        Then: Returns string with id and title
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        chapter = Chapter(
            episode_id=episode.id,
            chapter_index=0,
            title="第一章：介绍",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(chapter)
        test_session.flush()

        result = repr(chapter)

        assert "Chapter" in result
        assert f"id={chapter.id}" in result
        assert "第一章" in result
        assert "pending" in result
