"""MergeFidelity — Merge 保真度审计器。

用 git 自己的合并引擎复算"机械合并应该得到什么"，再与仓库里实际记录的树逐 blob
对比，挖出评审看不见的三类代码事故：夹带（evil merge）、静默吞掉（丢 hunk）、
跨分支漏搬。

本包只读 `.git`、零网络、零第三方运行时依赖。
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
