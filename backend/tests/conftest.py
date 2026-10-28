import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings,ROOT
from app.importer import import_dataset
from scripts.generate_fixtures import generate

@pytest.fixture(scope='session')
def starter_data(tmp_path_factory):
    root=tmp_path_factory.mktemp('starter-fixtures')
    generate(root)
    return root/'data'

@pytest.fixture
def app(tmp_path,starter_data):
    app=create_app(Settings(database_url='sqlite:///'+str(tmp_path/'test.db'),api_key='test-service-key',admin_api_key='test-admin-key'))
    with app.state.sessions() as db:
        import_dataset(db,starter_data);db.commit()
    yield app
    app.state.engine.dispose()

@pytest.fixture
def client(app):
    with TestClient(app,headers={'X-API-Key':'test-service-key'}) as client:
        yield client
