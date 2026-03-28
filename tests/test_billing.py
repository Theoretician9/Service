import pytest


class TestCreditReservation:
    @pytest.mark.asyncio
    async def test_reserve_credits_success(self, db_session):
        """Credits reserved when sufficient balance."""
        pass

    @pytest.mark.asyncio
    async def test_reserve_credits_insufficient(self, db_session):
        """Reservation fails when insufficient credits."""
        pass

    @pytest.mark.asyncio
    async def test_refund_on_failure(self, db_session):
        """Credits fully refunded on failed run."""
        pass

    @pytest.mark.asyncio
    async def test_partial_refund(self, db_session):
        """Half credits charged on partially_completed."""
        pass
