"""Candidate artifacts only. Trusted production activation is not implemented."""
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path, PurePosixPath

from .contracts import SourceManifest, valid_hash, valid_id, strict_int
from .errors import SazuError, require
from .sources import verify_file


@dataclass(frozen=True)
class Artifact:
    path: str
    sha256: str
    size_bytes: int

    def __post_init__(self):
        require(type(self.path) is str and 0 < len(self.path) <= 512)
        require(not self.path.startswith('/') and '\\' not in self.path
                and all(ord(c) >= 32 for c in self.path)
                and all(p not in ('', '.', '..') for p in self.path.split('/')))
        require(PurePosixPath(self.path).as_posix() == self.path)
        require(valid_hash(self.sha256) and strict_int(self.size_bytes, 0, 1 << 40))


@dataclass(frozen=True)
class DatasetCandidate:
    candidate_id: str
    coverage_start: date
    coverage_end: date
    zones: tuple[str, ...]
    artifacts: tuple[Artifact, ...]
    sources: tuple[SourceManifest, ...]
    evidence_ids: tuple[str, ...]
    status: str = field(default='candidate', init=False)
    production_authorized: bool = field(default=False, init=False)

    def __post_init__(self):
        require(valid_id(self.candidate_id))
        require(type(self.coverage_start) is date and type(self.coverage_end) is date
                and self.coverage_start <= self.coverage_end)
        require(type(self.zones) is tuple and bool(self.zones)
                and all(type(x) is str and 0 < len(x) <= 200 for x in self.zones))
        require(type(self.artifacts) is tuple and bool(self.artifacts)
                and all(type(a) is Artifact for a in self.artifacts))
        require(len({a.path for a in self.artifacts}) == len(self.artifacts))
        require(type(self.sources) is tuple and bool(self.sources)
                and all(type(m) is SourceManifest for m in self.sources))
        require(len({m.source_id for m in self.sources}) == len(self.sources))
        require(type(self.evidence_ids) is tuple and all(valid_id(x) for x in self.evidence_ids))


def verify_candidate_files(root: Path, candidate: DatasetCandidate) -> bool:
    require(type(candidate) is DatasetCandidate)
    root = Path(root).resolve(strict=True)
    for artifact in candidate.artifacts:
        path = root / artifact.path
        require(path.resolve().is_relative_to(root) and not path.is_symlink(), 'DATA_INTEGRITY_FAILED')
        # Reuse the bounded byte verifier; source provenance is not inferred here.
        m = replace(candidate.sources[0], sha256=artifact.sha256, size_bytes=artifact.size_bytes)
        verify_file(path, m)
    return True


def blockers(candidate: DatasetCandidate) -> tuple[str, ...]:
    require(type(candidate) is DatasetCandidate)
    result = ['TRUSTED_RELEASE_AUTHORIZATION_NOT_IMPLEMENTED']
    if any(m.rights_status != 'permitted' for m in candidate.sources):
        result.append('SOURCE_RIGHTS_NOT_APPROVED')
    if not candidate.evidence_ids:
        result.append('INDEPENDENT_VALIDATION_MISSING')
    # Evidence IDs are labels, not authenticated reports; never promote on this basis.
    result.append('EVIDENCE_CONTENT_AND_COVERAGE_NOT_AUTHENTICATED')
    return tuple(result)


def require_production_release(candidate: DatasetCandidate) -> None:
    require(type(candidate) is DatasetCandidate)
    raise SazuError('RELEASE_NOT_APPROVED')
