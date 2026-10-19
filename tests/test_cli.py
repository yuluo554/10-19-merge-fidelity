"""CLI 契约守门：子命令注册、退出码语义、中文错误信息、骨架期的"未实现"提示。"""

import pytest

from mergefidelity import __version__, cli
from mergefidelity.errors import EXIT_ENV, EXIT_OK, EXIT_USAGE, GitEnvError


def test_version_flag(capsys):
    code = cli.main(["--version"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert captured.out.strip() == "mergefidelity %s" % __version__


def test_no_arguments_prints_help_and_returns_usage(capsys):
    code = cli.main([])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "fidelity" in captured.err


def test_help_lists_all_subcommands(capsys):
    code = cli.main(["--help"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    for name in cli.SUBCOMMANDS:
        assert name in captured.out


def test_parser_registers_exactly_the_documented_subcommands():
    parser = cli.build_parser()
    actions = [a for a in parser._actions if a.dest == "command"]
    assert len(actions) == 1
    registered = set(actions[0].choices)
    assert registered == set(cli.SUBCOMMANDS)


@pytest.mark.parametrize("args", [
    ["fidelity", "--help"],
    ["fidelity", "scan", "--help"],
    ["parity", "--help"],
    ["ledger", "--help"],
    ["report", "--help"],
    ["gate", "--help"],
])
def test_subcommand_help_is_wellformed(args, capsys):
    code = cli.main(args)
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "usage:" in captured.out


def test_unknown_subcommand_returns_usage(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.build_parser().parse_args(["frobnicate"])
    assert excinfo.value.code == EXIT_USAGE


def test_fidelity_without_action_returns_usage(capsys):
    code = cli.main(["fidelity"])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "scan" in captured.err


@pytest.mark.parametrize("args,module,needle", [
    (["report", ".", "--verify", "no-such-report.json"], "report", "无法读取报告文件"),
    (["gate", ".", "--baseline", "no-such-baseline.toml"], "gate", "无法读取基线文件"),
])
def test_bad_input_files_return_usage_with_chinese_hint(args, module, needle, capsys):
    """坏输入文件必须以退出码 2 + 中文提示收场，绝不输出伪造空 JSON。

    （骨架期的"尚未实现"提示已随 M5 落地退役；这里守的是**输入类错误仍归 2**。）
    """
    code = cli.main(args)
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert needle in captured.err
    assert captured.out == ""


def test_missing_required_argument_exits_usage():
    with pytest.raises(SystemExit) as excinfo:
        cli.build_parser().parse_args(["parity"])
    assert excinfo.value.code == EXIT_USAGE


def test_git_env_error_maps_to_exit_code_3(monkeypatch, capsys):
    def boom(args):
        raise GitEnvError("模拟环境不满足")

    monkeypatch.setitem(cli._DISPATCH, "ledger", boom)
    code = cli.main(["ledger", "."])
    captured = capsys.readouterr()
    assert code == EXIT_ENV
    assert "模拟环境不满足" in captured.err


def test_dispatch_covers_every_subcommand():
    for name in cli.SUBCOMMANDS:
        assert name == "fidelity" or name in cli._DISPATCH
