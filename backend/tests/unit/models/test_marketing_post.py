"""
Unit tests for MarketingPost model.

Test Naming Convention (BDD):
- test_<behavior>_<expected_result>
"""
import pytest

from sqlalchemy.exc import IntegrityError

from app.models.marketing_post import MarketingPost
from app.models.chapter import Chapter
from app.models.episode import Episode


class TestMarketingPostCreate:
    """Test MarketingPost creation."""

    def test_marketing_post_create_minimal_fields(self, test_session):
        """Given: Database session and episode
        When: Creating MarketingPost with minimal fields
        Then: MarketingPost is created with correct defaults
        """
        episode = Episode(
            title="Test Episode",
            file_hash="abc123",
            duration=180.0,
        )
        test_session.add(episode)
        test_session.flush()

        post = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="干货硬核向",
            title="5分钟掌握商务英语",
            content="这是一篇关于商务英语学习的干货文章...",
        )
        test_session.add(post)
        test_session.flush()

        assert post.id is not None
        assert post.episode_id == episode.id
        assert post.platform == "xhs"
        assert post.angle_tag == "干货硬核向"
        assert post.title == "5分钟掌握商务英语"
        assert post.content == "这是一篇关于商务英语学习的干货文章..."
        assert post.chapter_id is None
        assert post.status == "pending"  # Default value

    def test_marketing_post_create_full_fields(self, test_session):
        """Given: Database session, episode, and chapter
        When: Creating MarketingPost with all fields
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
            chapter_index=0,
            title="第一章",
            start_time=0.0,
            end_time=30.0,
        )
        test_session.add(chapter)
        test_session.flush()

        post = MarketingPost(
            episode_id=episode.id,
            chapter_id=chapter.id,
            platform="twitter",
            angle_tag="搞笑吐槽向",
            title="搞笑解读：老外学中文的迷惑行为",
            content="这是一个关于语言学习的搞笑视频...",
            status="completed",
        )
        test_session.add(post)
        test_session.flush()

        assert post.episode_id == episode.id
        assert post.chapter_id == chapter.id
        assert post.platform == "twitter"
        assert post.angle_tag == "搞笑吐槽向"
        assert post.title == "搞笑解读：老外学中文的迷惑行为"
        assert post.content == "这是一个关于语言学习的搞笑视频..."
        assert post.status == "completed"

    def test_marketing_post_status_default_is_pending(self, test_session):
        """Given: New MarketingPost
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

        post = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="干货硬核向",
            title="Test",
            content="Test content",
        )
        test_session.add(post)
        test_session.flush()

        assert post.status == "pending"


class TestMarketingPostConstraints:
    """Test MarketingPost database constraints."""

    def test_marketing_post_episode_id_not_null_constraint(self, test_session):
        """Given: MarketingPost without episode_id
        When: Attempting to save
        Then: Raises IntegrityError
        """
        post = MarketingPost(
            # episode_id is missing
            platform="xhs",
            angle_tag="干货硬核向",
            title="Test",
            content="Test content",
        )
        test_session.add(post)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_marketing_post_platform_not_null_constraint(self, test_session):
        """Given: MarketingPost without platform
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

        post = MarketingPost(
            episode_id=episode.id,
            # platform is missing
            angle_tag="干货硬核向",
            title="Test",
            content="Test content",
        )
        test_session.add(post)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_marketing_post_angle_tag_not_null_constraint(self, test_session):
        """Given: MarketingPost without angle_tag
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

        post = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            # angle_tag is missing
            title="Test",
            content="Test content",
        )
        test_session.add(post)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_marketing_post_title_not_null_constraint(self, test_session):
        """Given: MarketingPost without title
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

        post = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="干货硬核向",
            # title is missing
            content="Test content",
        )
        test_session.add(post)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_marketing_post_content_not_null_constraint(self, test_session):
        """Given: MarketingPost without content
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

        post = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="干货硬核向",
            title="Test",
            # content is missing
        )
        test_session.add(post)

        with pytest.raises(IntegrityError):
            test_session.flush()

    def test_marketing_post_no_unique_constraint_allows_duplicates(self, test_session):
        """Given: Episode with existing marketing post
        When: Creating multiple posts with same episode_id, platform, and angle_tag
        Then: All posts are created successfully (Content Racing design)
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        # Create multiple posts with same values (Content Racing: 1:N stacking)
        post1 = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="干货硬核向",
            title="Post 1",
            content="Content 1",
        )
        post2 = MarketingPost(
            episode_id=episode.id,
            platform="xhs",  # Same platform
            angle_tag="干货硬核向",  # Same angle
            title="Post 2",
            content="Content 2",
        )
        test_session.add(post1)
        test_session.add(post2)
        test_session.flush()

        assert post1.id is not None
        assert post2.id is not None
        assert post1.id != post2.id  # Different IDs


class TestMarketingPostRelationships:
    """Test MarketingPost relationships."""

    def test_marketing_post_belongs_to_episode(self, test_session):
        """Given: MarketingPost with episode_id
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

        post = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="干货硬核向",
            title="Test",
            content="Test content",
        )
        test_session.add(post)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(post)
        test_session.refresh(episode)

        assert post.episode.id == episode.id
        assert post.episode.title == "Test Episode"

    def test_marketing_post_belongs_to_chapter(self, test_session):
        """Given: MarketingPost with chapter_id
        When: Accessing chapter relationship
        Then: Returns correct Chapter object
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

        post = MarketingPost(
            episode_id=episode.id,
            chapter_id=chapter.id,
            platform="xhs",
            angle_tag="干货硬核向",
            title="Test",
            content="Test content",
        )
        test_session.add(post)
        test_session.flush()

        # Refresh to load relationship
        test_session.refresh(post)
        test_session.refresh(chapter)

        assert post.chapter.id == chapter.id
        assert post.chapter.title == "第一章"


class TestMarketingPostRepr:
    """Test MarketingPost __repr__ method."""

    def test_marketing_post_repr_contains_id_and_platform(self, test_session):
        """Given: MarketingPost object
        When: Calling repr()
        Then: Returns string with id and platform
        """
        episode = Episode(
            title="Test Episode",
            file_hash="test123",
            duration=100.0,
        )
        test_session.add(episode)
        test_session.flush()

        post = MarketingPost(
            episode_id=episode.id,
            platform="xhs",
            angle_tag="干货硬核向",
            title="Test Post",
            content="Test content",
        )
        test_session.add(post)
        test_session.flush()

        result = repr(post)

        assert "MarketingPost" in result
        assert f"id={post.id}" in result
        assert "xhs" in result
        assert "干货硬核向" in result
