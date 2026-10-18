"""退出码常量与项目自有异常。

退出码契约（plan/03 §0，全项目唯一表）：

    0  成功且无"需失败"的发现
    1  成功执行，但存在需失败的发现（gate 新增/过期；fidelity --fail-on 命中）
    2  用法错误：未知子命令、缺必填参数、坏基线语法、坏报告文件、本构建未实现的模块
    3  环境不满足：git 版本低于门槛、仓库不存在/不是 git 仓库、git 调用超时

任何模块都不得自行 `sys.exit`；只抛异常，由 `mergefidelity.cli.main` 统一映射。
"""

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_ENV = 3


class MergeFidelityError(Exception):
    """项目自有异常基类。"""

    exit_code = EXIT_USAGE


class UsageError(MergeFidelityError):
    """用法/输入错误 → 退出码 2。"""

    exit_code = EXIT_USAGE


class NotReadyError(MergeFidelityError):
    """本构建尚未包含该模块（骨架期）。

    骨架期专用：每个模块落地时**同轮退役**对应的 raise（见 plan/05 里程碑表）。
    绝不用于"输入有问题"，也绝不返回伪造的空结果。
    """

    exit_code = EXIT_USAGE

    def __init__(self, module, planned):
        self.module = module
        self.planned = planned
        super().__init__(
            "%s：该子命令在本构建（%s）中尚未实现，计划于%s落地。"
            % (module, "0.1.0.dev0", planned)
        )


class GitEnvError(MergeFidelityError):
    """环境不满足 → 退出码 3。"""

    exit_code = EXIT_ENV
