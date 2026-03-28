import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def db_session():
    """Provide a test database session."""
    # TODO: setup test database, create tables, yield session, rollback
    pass


@pytest.fixture
def sample_user_data():
    return {
        "telegram_id": 123456789,
        "first_name": "Test",
        "username": "testuser",
    }


@pytest.fixture
def sample_project_data():
    return {
        "name": "Test Project",
        "description": "Test description",
    }
