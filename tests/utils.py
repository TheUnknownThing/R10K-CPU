import contextlib
import io
import os
from typing import Any, Callable


def run_quietly(func: Callable[[Any], Any], *args, **kwargs) -> tuple[Any | None, str, str]:
    """Runs a function while capturing all output."""
    """The original version is from assassyn."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    result = None

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            with open(os.devnull, "w") as devnull:
                # 重定向原始文件描述符，捕获低层系统调用的输出
                old_stdout = os.dup(1)
                old_stderr = os.dup(2)
                os.dup2(devnull.fileno(), 1)
                os.dup2(devnull.fileno(), 2)
                try:
                    result = func(*args, **kwargs)
                finally:
                    os.dup2(old_stdout, 1)
                    os.dup2(old_stderr, 2)
        except Exception as e:
            stderr.write(f"Error: {str(e)}\n")

    return result, stdout.getvalue(), stderr.getvalue()
