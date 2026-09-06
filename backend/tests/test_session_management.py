import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from datetime import datetime

from app.crud.session import (
    list_user_sessions,
    delete_session,
    update_session_title,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_list_user_sessions_with_mock():
    mock_db = AsyncMock()

    # Session with custom title in _meta
    sess1 = SimpleNamespace(
        id="sess_custom",
        user_id=1,
        phase="START",
        slots={"_meta": {"title": "成都旅游攻略"}},
        created_at=datetime(2026, 9, 6, 10, 0, 0),
        updated_at=datetime(2026, 9, 6, 12, 0, 0),
    )

    # Session without title in _meta
    sess2 = SimpleNamespace(
        id="sess_auto",
        user_id=1,
        phase="PLAN",
        slots={"_meta": {}},
        created_at=datetime(2026, 9, 6, 9, 0, 0),
        updated_at=datetime(2026, 9, 6, 11, 0, 0),
    )

    # Mock execute results
    # 1. select SessionRow
    mock_res_sessions = MagicMock()
    mock_res_sessions.scalars.return_value.all.return_value = [sess1, sess2]

    # 2. select count for sess1
    mock_cnt1 = MagicMock()
    mock_cnt1.scalar.return_value = 3

    # 3. select first user msg for sess2
    mock_first_msg = MagicMock()
    mock_first_msg.scalars.return_value.first.return_value = "帮我规划上海到杭州的高铁"

    # 4. select count for sess2
    mock_cnt2 = MagicMock()
    mock_cnt2.scalar.return_value = 2

    mock_db.execute.side_effect = [
        mock_res_sessions,
        mock_cnt1,
        mock_first_msg,
        mock_cnt2,
    ]

    sessions = await list_user_sessions(mock_db, user_id=1)
    assert len(sessions) == 2
    assert sessions[0]["sessionId"] == "sess_custom"
    assert sessions[0]["title"] == "成都旅游攻略"
    assert sessions[0]["messageCount"] == 3

    assert sessions[1]["sessionId"] == "sess_auto"
    assert sessions[1]["title"] == "帮我规划上海到杭州的高铁"
    assert sessions[1]["messageCount"] == 2


@pytest.mark.anyio
async def test_update_session_title_mock():
    mock_db = AsyncMock()
    sess = SimpleNamespace(
        id="sess_123",
        user_id=1,
        slots={"_meta": {}},
        updated_at=None,
    )
    mock_res = MagicMock()
    mock_res.scalars.return_value.first.return_value = sess
    mock_db.execute.return_value = mock_res

    ok = await update_session_title(mock_db, "sess_123", 1, "新标题")
    assert ok is True
    assert sess.slots["_meta"]["title"] == "新标题"
    mock_db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_delete_session_mock():
    mock_db = AsyncMock()
    sess = SimpleNamespace(
        id="sess_del",
        user_id=1,
    )
    mock_res = MagicMock()
    mock_res.scalars.return_value.first.return_value = sess
    mock_db.execute.return_value = mock_res

    ok = await delete_session(mock_db, "sess_del", 1)
    assert ok is True
    mock_db.delete.assert_awaited_once_with(sess)
    mock_db.commit.assert_awaited_once()
