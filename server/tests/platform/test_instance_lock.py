import pytest

from whaat.platform.instance_lock import InstanceRunningError, bind_listener


def test_a_second_listener_on_the_same_port_is_refused() -> None:
    first = bind_listener("127.0.0.1", 0)
    port = first.getsockname()[1]
    try:
        with pytest.raises(InstanceRunningError):
            bind_listener("127.0.0.1", port)
    finally:
        first.close()
    bind_listener("127.0.0.1", port).close()
