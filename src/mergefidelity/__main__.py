"""`python -m mergefidelity` 入口。

注意：`argparse` 的 `SystemExit(2)` 由 `main()` 转成返回值，这里统一
`sys.exit()`；缺了这个文件，`python -m mergefidelity` 会报
`No module named mergefidelity.__main__`。
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
