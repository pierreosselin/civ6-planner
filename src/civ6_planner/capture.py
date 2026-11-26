"""Capture what C code (HiGHS) prints to the process's stdout, as text, optionally
passing it on to the terminal as it comes."""
import contextlib
import os
import pty
import sys
import termios
import threading
from typing import Iterator


class _Captured:
    def __init__(self):
        self.text = ""

    def read(self):
        return self.text


@contextlib.contextmanager
def capture_stdout(tee: bool = False) -> Iterator[_Captured]:
    """Capture what C code (HiGHS) prints to file descriptor 1; with tee, also pass it on
    to the real stdout as it comes. A pseudo-terminal, not a pipe, so the C library
    keeps line buffering and the log appears line by line."""
    out = _Captured()
    sys.stdout.flush()
    saved = os.dup(1)
    master, slave = pty.openpty()
    attrs = termios.tcgetattr(slave)
    attrs[1] &= ~termios.ONLCR                      # keep "\n", don't turn it into "\r\n"
    termios.tcsetattr(slave, termios.TCSANOW, attrs)
    chunks: list[bytes] = []

    def pump() -> None:
        while True:
            try:
                data = os.read(master, 4096)
            except OSError:                         # EIO: the slave side is closed
                break
            if not data:
                break
            chunks.append(data)
            if tee:
                os.write(saved, data)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    os.dup2(slave, 1)
    os.close(slave)
    try:
        yield out
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)                           # closes the last handle on the slave side
        reader.join(timeout=5)
        os.close(master)
        os.close(saved)
        out.text = b"".join(chunks).decode("utf-8", "replace")
