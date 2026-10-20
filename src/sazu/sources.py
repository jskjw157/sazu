"""Integrity checks and explicit, bounded batch acquisition; never runtime fallback."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import stat
import tempfile
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .contracts import SourceManifest, public_url, strict_int
from .errors import SazuError, require


@dataclass(frozen=True)
class AcquisitionPolicy:
    max_bytes: int = 64 * 1024 * 1024
    timeout: float = 20.0
    attempts: int = 3
    redirects: int = 3

    def __post_init__(self):
        require(strict_int(self.max_bytes, 1, 256 * 1024 * 1024))
        require(type(self.timeout) in (int, float) and math.isfinite(self.timeout)
                and 0 < self.timeout <= 120)
        require(strict_int(self.attempts, 1, 3) and strict_int(self.redirects, 0, 3))


OFFICIAL_HOSTS = frozenset({'naif.jpl.nasa.gov', 'ssd.jpl.nasa.gov', 'astro.kasi.re.kr'})


def verify_file(path: Path, manifest: SourceManifest) -> str:
    """Verify actual bytes using a no-follow descriptor. Parent directory is trusted."""
    require(type(manifest) is SourceManifest)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except FileNotFoundError:
        raise SazuError('SOURCE_NOT_AVAILABLE') from None
    except OSError:
        raise SazuError('DATA_INTEGRITY_FAILED') from None
    try:
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size == manifest.size_bytes,
                    'DATA_INTEGRITY_FAILED')
            hasher = hashlib.sha256()
            count = 0
            while chunk := stream.read(min(65536, manifest.size_bytes - count + 1)):
                count += len(chunk)
                require(count <= manifest.size_bytes, 'DATA_INTEGRITY_FAILED')
                hasher.update(chunk)
            require(count == manifest.size_bytes and hasher.hexdigest() == manifest.sha256,
                    'DATA_INTEGRITY_FAILED')
            return hasher.hexdigest()
    except OSError:
        raise SazuError('DATA_INTEGRITY_FAILED') from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@contextmanager
def _https_transport(url, timeout):
    # No ambient proxy credentials and no implicit redirect following.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    request = Request(url, headers={'User-Agent': 'sazu-source-acquisition/0.1'})
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        yield response


def _allowed(url: str) -> None:
    require(public_url(url))
    require(urlsplit(url).hostname in OFFICIAL_HOSTS)


def acquire_source(url: str, target: Path, manifest: SourceManifest,
                   policy: AcquisitionPolicy = AcquisitionPolicy(),
                   transport=None) -> str:
    """Explicit batch operation. Hash and size must already come from a manifest.

    A supplied manifest is a checksum assertion, not provider authentication or
    a license grant. Destination parents must be controlled by the operator.
    Publication never overwrites an existing target, including a concurrent one.
    """
    require(type(manifest) is SourceManifest and type(policy) is AcquisitionPolicy)
    _allowed(url)
    require(url == manifest.url and manifest.size_bytes <= policy.max_bytes)
    target = Path(target)
    require(target.name not in {'', '.', '..'} and not target.exists() and not target.is_symlink())
    require(target.parent.is_dir(), 'SOURCE_NOT_AVAILABLE')
    open_transport = transport or _https_transport
    for attempt in range(policy.attempts):
        temporary = None
        try:
            current = url
            for redirects in range(policy.redirects + 1):
                _allowed(current)
                with open_transport(current, policy.timeout) as response:
                    status = response.status
                    if status in (301, 302, 303, 307, 308):
                        require(redirects < policy.redirects, 'ACQUISITION_FAILED')
                        location = response.headers.get('Location')
                        require(type(location) is str, 'ACQUISITION_FAILED')
                        current = urljoin(current, location)
                        _allowed(current)
                        continue
                    require(status == 200, 'ACQUISITION_FAILED')
                    length = response.headers.get('Content-Length')
                    if length is not None:
                        require(str(length).isdigit() and int(length) == manifest.size_bytes,
                                'DATA_INTEGRITY_FAILED')
                    fd, name = tempfile.mkstemp(prefix='.sazu-', dir=target.parent)
                    temporary = Path(name)
                    with os.fdopen(fd, 'wb') as out:
                        hasher = hashlib.sha256()
                        count = 0
                        while chunk := response.read(min(65536, manifest.size_bytes - count + 1)):
                            require(type(chunk) is bytes, 'DATA_INTEGRITY_FAILED')
                            count += len(chunk)
                            require(count <= manifest.size_bytes, 'DATA_INTEGRITY_FAILED')
                            out.write(chunk)
                            hasher.update(chunk)
                        require(count == manifest.size_bytes and hasher.hexdigest() == manifest.sha256,
                                'DATA_INTEGRITY_FAILED')
                        out.flush()
                        os.fsync(out.fileno())
                    # An atomic hard-link provides no-clobber publication.
                    os.link(temporary, target)
                    return hasher.hexdigest()
            raise SazuError('ACQUISITION_FAILED')
        except SazuError:
            raise
        except (OSError, TimeoutError):
            if attempt + 1 == policy.attempts:
                raise SazuError('ACQUISITION_FAILED') from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    raise SazuError('ACQUISITION_FAILED')
