"""Stable public errors. Never incorporate raw input or dependency exceptions."""

_MESSAGES = {
    'INVALID_INPUT': 'Input does not satisfy the explicit contract.',
    'UNSUPPORTED_RANGE': 'Input is outside the declared computational range.',
    'UNSUPPORTED_TIMEZONE_RULE': 'Timezone rule cannot be expanded safely.',
    'NONEXISTENT_LOCAL_TIME': 'Local time has no corresponding UTC instant.',
    'SOURCE_NOT_AVAILABLE': 'Required local source is unavailable.',
    'DATA_INTEGRITY_FAILED': 'Source integrity or structure validation failed.',
    'RELEASE_NOT_APPROVED': 'Production release authorization is unavailable.',
    'SOURCE_CONFLICT': 'Reference sources or versions conflict.',
    'ACQUISITION_FAILED': 'Source acquisition failed without publication.',
    'REQUEST_TOO_LARGE': 'Request exceeds the allowed size.',
    'INTERNAL_ERROR': 'The operation could not be completed.',
}


class SazuError(ValueError):
    """Only known codes can cross the public boundary."""

    def __init__(self, code: str):
        self.code = code if code in _MESSAGES else 'INTERNAL_ERROR'
        super().__init__(_MESSAGES[self.code])

    def as_dict(self) -> dict[str, object]:
        return {'code': self.code, 'message': str(self),
                'retryable': self.code == 'ACQUISITION_FAILED'}


def require(condition: bool, code: str = 'INVALID_INPUT') -> None:
    if not condition:
        raise SazuError(code)
