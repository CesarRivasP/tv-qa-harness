from unittest.mock import patch, MagicMock
from tvqa.proxy import ProxyHarness


def test_start_launches_mitmdump_and_sets_device_proxy():
    with patch("subprocess.Popen") as popen, patch("subprocess.run") as run:
        popen.return_value = MagicMock(pid=1234)
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # → _facts.yml: infra.default_serial / proxy_host_ip / proxy_port
        harness = ProxyHarness(serial="emulator-5554", host_ip="10.0.2.2", port=8080)
        harness.start(addon_path="epic_stall_test.py", env={"EPIC_MODE": "origin403"})

        popen_cmd = popen.call_args[0][0]
        assert popen_cmd[:2] == ["mitmdump", "-s"]
        assert "epic_stall_test.py" in popen_cmd

        set_proxy_call = [c for c in run.call_args_list if "http_proxy" in " ".join(c[0][0])][0]
        assert "10.0.2.2:8080" in " ".join(set_proxy_call[0][0])


def test_stop_clears_all_three_proxy_keys_and_kills_process():
    with patch("subprocess.Popen") as popen, patch("subprocess.run") as run:
        popen.return_value = MagicMock(pid=1234)
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # → _facts.yml: infra.default_serial / proxy_host_ip / proxy_port
        harness = ProxyHarness(serial="emulator-5554", host_ip="10.0.2.2", port=8080)
        harness.start(addon_path="epic_stall_test.py", env={"EPIC_MODE": "origin403"})
        harness.stop()

        deleted_keys = set()
        for call in run.call_args_list:
            args = " ".join(call[0][0])
            if "settings delete global" in args:
                deleted_keys.add(args.split()[-1])
        assert deleted_keys == {"http_proxy", "global_http_proxy_host", "global_http_proxy_port"}
