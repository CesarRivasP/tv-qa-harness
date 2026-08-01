import subprocess
import time
from unittest.mock import patch, MagicMock

from tvqa.logwait import wait_for_line, LogWaitTimeout


def _fake_popen_lines(lines, delay=0.01):
    proc = MagicMock()
    def _iter():
        for line in lines:
            time.sleep(delay)
            yield line
    proc.stdout = _iter()
    proc.poll.return_value = None
    proc.terminate = MagicMock()
    return proc


def test_wait_for_line_returns_matching_line():
    lines = [
        "some noise\n",
        "self-heal on network return (exhausted)\n",
        "more noise\n",
    ]
    # wait_for_line first clears the ring buffer (`logcat -c`) via subprocess.run so it
    # never matches stale backlog; mock that away and only drive the tailing Popen.
    with patch("subprocess.run", return_value=MagicMock()), \
            patch("subprocess.Popen", return_value=_fake_popen_lines(lines)):
        result = wait_for_line(pattern=r"self-heal.*exhausted", timeout_s=2, serial="emulator-5554")
    assert "self-heal" in result.line
    assert result.matched is True


def test_wait_for_line_times_out_with_no_match():
    lines = ["irrelevant\n"] * 3
    with patch("subprocess.run", return_value=MagicMock()), \
            patch("subprocess.Popen", return_value=_fake_popen_lines(lines, delay=0.01)):
        try:
            wait_for_line(pattern=r"never-appears", timeout_s=0.05, serial="emulator-5554")
            assert False, "expected LogWaitTimeout"
        except LogWaitTimeout:
            pass


def test_wait_for_line_clears_buffer_before_tailing():
    """Regression: a stale backlog line must not match. The buffer is cleared first."""
    calls = []

    def _record_run(args, **kwargs):
        calls.append(args)
        return MagicMock()

    lines = ["fresh playerFailed\n"]
    with patch("subprocess.run", side_effect=_record_run), \
            patch("subprocess.Popen", return_value=_fake_popen_lines(lines)):
        wait_for_line(pattern=r"playerFailed", timeout_s=2, serial="emulator-5554")

    assert any("logcat" in a and "-c" in a for a in calls), "expected a `logcat -c` buffer clear"
