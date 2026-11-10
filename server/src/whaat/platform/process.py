import subprocess
from typing import IO


def spawn_detached(args: list[str], log: IO[bytes]) -> None:
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
