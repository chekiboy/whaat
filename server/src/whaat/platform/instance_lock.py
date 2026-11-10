import socket


class InstanceRunningError(Exception):
    def __init__(self, host: str, port: int) -> None:
        super().__init__(f"another server already listens on {host}:{port}")
        self.host = host
        self.port = port


def bind_listener(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        sock.listen()
    except OSError as err:
        sock.close()
        raise InstanceRunningError(host, port) from err
    return sock
