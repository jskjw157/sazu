from contextlib import contextmanager
from hashlib import sha256
import io
import pytest
from tests.test_core import manifest
from sazu.errors import SazuError


def fixture(data=b'abc'):
    return manifest(sha256=sha256(data).hexdigest(),size_bytes=len(data))

@contextmanager
def transport_ok(url, timeout):
    result=io.BytesIO(b'abc'); result.status=200; result.headers={'Content-Length':'3'}
    yield result


def test_verify_content_and_missing(tmp_path):
    from sazu.sources import verify_file
    p=tmp_path/'data'; p.write_bytes(b'abc')
    assert verify_file(p,fixture())==fixture().sha256
    with pytest.raises(SazuError) as e: verify_file(tmp_path/'absent',fixture())
    assert e.value.code=='SOURCE_NOT_AVAILABLE'

@pytest.mark.parametrize('data',[b'ab',b'abcd',b'xyz'])
def test_corrupt_file(tmp_path,data):
    from sazu.sources import verify_file
    p=tmp_path/'data'; p.write_bytes(data)
    with pytest.raises(SazuError) as e: verify_file(p,fixture())
    assert e.value.code=='DATA_INTEGRITY_FAILED'

def test_no_symlink(tmp_path):
    from sazu.sources import verify_file
    p=tmp_path/'real'; p.write_bytes(b'abc'); link=tmp_path/'link'; link.symlink_to(p)
    with pytest.raises(SazuError): verify_file(link,fixture())

def test_acquire_atomic_no_overwrite(tmp_path):
    from sazu.sources import acquire_source
    p=tmp_path/'data'
    assert acquire_source(fixture().url,p,fixture(),transport=transport_ok)==fixture().sha256
    assert p.read_bytes()==b'abc'
    with pytest.raises(SazuError): acquire_source(fixture().url,p,fixture(),transport=transport_ok)
    assert [x.name for x in tmp_path.iterdir()]==['data']

@pytest.mark.parametrize('data',[b'ab',b'abcd',b'xyz'])
def test_bad_download_never_published(tmp_path,data):
    from sazu.sources import acquire_source
    @contextmanager
    def transport(url, timeout):
        r=io.BytesIO(data);r.status=200;r.headers={};yield r
    with pytest.raises(SazuError): acquire_source(fixture().url,tmp_path/'data',fixture(),transport=transport)
    assert list(tmp_path.iterdir())==[]

@pytest.mark.parametrize('url',['http://astro.kasi.re.kr/x','https://evil.example/x',
                               'https://127.0.0.1/x','https://astro.kasi.re.kr.evil/x',
                               'https://astro.kasi.re.kr/x?key=secret','https://user@astro.kasi.re.kr/x'])
def test_disallowed_url(tmp_path,url):
    from sazu.sources import acquire_source
    with pytest.raises(SazuError): acquire_source(url,tmp_path/'data',fixture(),transport=transport_ok)
    assert not list(tmp_path.iterdir())

def test_redirect_revalidated(tmp_path):
    from sazu.sources import acquire_source
    @contextmanager
    def transport(url, timeout):
        r=io.BytesIO();r.status=302;r.headers={'Location':'https://evil.example/file'};yield r
    with pytest.raises(SazuError): acquire_source(fixture().url,tmp_path/'data',fixture(),transport=transport)
    assert not list(tmp_path.iterdir())

def test_bounded_retry(tmp_path):
    from sazu.sources import acquire_source,AcquisitionPolicy
    calls=[]
    @contextmanager
    def transport(url, timeout):
        calls.append(url);raise TimeoutError('secret');yield
    with pytest.raises(SazuError) as e:
        acquire_source(fixture().url,tmp_path/'data',fixture(),AcquisitionPolicy(attempts=2),transport)
    assert len(calls)==2 and e.value.code=='ACQUISITION_FAILED'
    assert 'secret' not in str(e.value) and not list(tmp_path.iterdir())

def test_policy_limits():
    from sazu.sources import AcquisitionPolicy
    for kwargs in ({'attempts':0},{'attempts':True},{'max_bytes':-1},{'timeout':float('inf')}):
        with pytest.raises(SazuError): AcquisitionPolicy(**kwargs)

def test_fifo_rejected_without_blocking(tmp_path,monkeypatch):
    import os
    from sazu.sources import verify_file
    fifo=tmp_path/'fifo';os.mkfifo(fifo)
    real_open=os.open
    def audited_open(path,flags,*args,**kwargs):
        assert flags & os.O_NONBLOCK
        return real_open(path,flags,*args,**kwargs)
    monkeypatch.setattr(os,'open',audited_open)
    with pytest.raises(SazuError) as e: verify_file(fifo,fixture())
    assert e.value.code=='DATA_INTEGRITY_FAILED'
