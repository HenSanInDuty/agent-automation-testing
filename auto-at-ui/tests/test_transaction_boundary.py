import pytest
from infrastructure.persistence.session import transactional_session


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_transaction_commits_and_closes_after_success() -> None:
    session = FakeSession()

    with transactional_session(lambda: session) as actual:
        assert actual is session

    assert session.committed
    assert not session.rolled_back
    assert session.closed


def test_transaction_rolls_back_and_closes_after_error() -> None:
    session = FakeSession()

    with pytest.raises(RuntimeError, match="boom"):
        with transactional_session(lambda: session):
            raise RuntimeError("boom")

    assert not session.committed
    assert session.rolled_back
    assert session.closed
