from dataclasses import dataclass
from typing import Optional


@dataclass
class ErrorInfo:
    code: str
    message: str
    retryable: bool = False
    backoff_ms: Optional[int] = None


ERRORS: dict[str, ErrorInfo] = {
    "ESEQ_RETRY": ErrorInfo("ESEQ_RETRY", "sequence gap, retry fragment", True, 20),
    "ETIMEOUT": ErrorInfo("ETIMEOUT", "adapter timeout", True, 100),
    "ECIRCUIT": ErrorInfo("ECIRCUIT", "circuit open", True, 200),
    "EPOLICY": ErrorInfo("EPOLICY", "policy denied", False, None),
    "EBAD_INPUT": ErrorInfo("EBAD_INPUT", "invalid frame/payload", False, None),
    "ECONTEXT": ErrorInfo("ECONTEXT", "context/window exceeded", True, 50),
    "EADAPTER": ErrorInfo("EADAPTER", "adapter 5xx", True, 80),
}


def error(code: str, detail: Optional[str] = None) -> dict:
    info = ERRORS.get(code, ErrorInfo(code, "unknown error", False, None))
    out = {
        "code": info.code,
        "message": info.message,
        "retryable": info.retryable,
    }
    if info.backoff_ms is not None:
        out["backoff_ms"] = info.backoff_ms
    if detail:
        out["detail"] = detail
    return out
