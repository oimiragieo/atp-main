import random
import time
from collections.abc import Callable


def fault_injector(
    op: Callable[[], None], p_error: float = 0.1, p_delay: float = 0.2, delay_ms: int = 50
) -> Callable[[], None]:
    def wrapped():
        r = random.random()
        if r < p_error:
            raise RuntimeError("injected error")
        if r < p_error + p_delay:
            time.sleep(delay_ms / 1000.0)
        return op()

    return wrapped
