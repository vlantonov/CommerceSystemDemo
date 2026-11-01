"""OpenAPI contract tests powered by Schemathesis."""

import pytest
import pytest_asyncio
import schemathesis
from httpx import ASGITransport, AsyncClient
from hypothesis import HealthCheck, settings

from app.db.session import create_schema, drop_schema, get_engine, get_session_factory
from app.main import create_app

schema = schemathesis.openapi.from_dict(create_app().openapi())


@pytest_asyncio.fixture(autouse=True)
async def reset_database_schema():
    """Ensure schema exists for ASGI-transport contract checks."""
    await drop_schema()
    await create_schema()


@pytest.fixture
async def contract_client():
    """Create ASGI client without running application lifespan."""
    app = create_app()
    app.state.engine = get_engine()
    app.state.session_factory = get_session_factory()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.contract
@settings(
    max_examples=3,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@schema.parametrize()
async def test_openapi_contract(case, contract_client: AsyncClient):
    """Validate generated API interactions against the OpenAPI contract."""
    request_kwargs = case.as_transport_kwargs(base_url=str(contract_client.base_url))
    response = await contract_client.request(**request_kwargs)
    case.validate_response(
        response,
        checks=[
            schemathesis.checks.not_a_server_error,
            schemathesis.checks.status_code_conformance,
            schemathesis.checks.response_schema_conformance,
        ],
    )
