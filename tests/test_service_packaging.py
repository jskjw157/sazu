"""Static safety contracts; running containers is a separate CI check."""
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]


def compose():
    path=ROOT/'compose.yaml'
    assert path.exists(), 'Isolated service topology is not implemented'
    return yaml.safe_load(path.read_text())


def test_only_gateway_port_is_published_to_loopback():
    services=compose()['services']
    assert services['api']['ports']==['127.0.0.1:3000:3000']
    assert not services['calculator'].get('ports')
    assert not services['postgres'].get('ports')


def test_calculator_cannot_join_database_or_external_network():
    c=compose()
    assert c['services']['calculator']['networks']==['compute']
    assert c['networks']['compute']['internal'] is True
    assert c['networks']['storage']['internal'] is True
    assert c['services']['postgres']['networks']==['storage']
    assert set(c['services']['api']['networks'])=={'edge','compute','storage'}


def test_credentials_are_separate_and_required():
    c=compose()['services']
    assert 'DATABASE_URL' not in c['calculator']['environment']
    assert 'RESEARCH_API_TOKEN' not in c['calculator']['environment']
    assert '${CALCULATOR_TOKEN:?' in c['calculator']['environment']['CALCULATOR_TOKEN']
    assert 'sazu_app:' in c['api']['environment']['DATABASE_URL']
    assert 'POSTGRES_ADMIN_PASSWORD' not in str(c['api']['environment'])


def test_app_containers_nonroot_readonly_no_privileges():
    c=compose()['services']
    for name in ('api','calculator'):
        assert c[name]['read_only'] is True
        assert c[name]['cap_drop']==['ALL']
        assert c[name]['security_opt']==['no-new-privileges:true']
    assert 'USER node' in (ROOT/'apps/api/Dockerfile').read_text()
    assert 'USER 10001:10001' in (ROOT/'infra/calculator.Dockerfile').read_text()


def test_no_root_database_role_or_personal_data_schema_for_api():
    p=ROOT/'infra/postgres/001-role.sql'
    assert p.exists(), 'Database role bootstrap is not implemented'
    text=p.read_text()
    assert 'NOSUPERUSER NOCREATEDB NOCREATEROLE' in text
    assert 'REVOKE ALL ON DATABASE sazu FROM PUBLIC' in text
    assert 'CREATE TABLE' not in text
