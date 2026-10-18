# HANDOFF-M3 · 下一棒：`parity`（跨分支补丁对齐）

> 本文件由 M2 收尾时写入。上游：`plan/05-里程碑.md` 的 M3 行、`data/README.md` §4.4。
> 用法：新对话 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务`。

## 1. 当前进度与证据（M2 已完成）

| 项 | 状态 | 证据（2026-10-18 实测） |
|---|---|---|
| `fidelity scan` 实现 | ✅ | `src/mergefidelity/fidelity.py`：枚举 → 单进程 remerge payload → `MechanicalMerge`（对象隔离）→ `blob_fidelity` → 三类 hunk → `--show-kind/--show-resolution/--fail-on/--format/--out/--as-of` |
| golden 逐项一致 | ✅ | **12/12** fidelity fixture（`tests/test_fidelity.py`，参数化逐 fixture + 逐字段） |
| SKIPPED 语义 | ✅ | octopus（父提交数 >2）与 custom_driver（`.gitattributes` + 路径命中）均显式记录、不进分母、**退出码 0** |
| 反例不误报 | ✅ | `clean-resolution-a/b`、`drop-then-readd`、`custom-driver` 断言 `smuggled=0 且 dropped=0` |
| 确定性 | ✅ | 同仓双跑逐字节一致；`digest` 可复算（`canonical.verify_digest`）；报告 0 绝对路径、`as_of` 来自提交时间 |
| 骨架态退役 | ✅ | `fidelity.py` 的 `NotReadyError` 已删；骨架登记测试同步缩小（现只剩 parity/ledger/report/gate） |
| 基准 | ✅ | `bench/fidelity.json`：12 fixture 省时 + 8-merge 合成仓**批量 0.061 s vs 逐 merge 0.463 s（≈7.6×）** |
| CI 接线 | ✅ | 新增 step `CLI smoke (fidelity on generated fixtures)`（`shell: bash` + `set +e` + 显式断言退出码 1）；workflow 本地 `yaml.safe_load` 通过（7 step） |
| 测试规模 | ✅ | 快层 **125 passed** ×（3.8 / 3.12）；慢层（`--check` 重生成 21 个仓库）1 passed |

**本地等价校验（未接远端，CI 待首推验证）**：双解释器快层、3.8 慢层、`--check` CLI 实跑、workflow 本地解析。
**不可本机实跑**：Linux/macOS 行为差异与 runner 的编码/路径形态。

## 2. 下一棒待办（M3 = parity）

1. **实现 `mergefidelity parity <repo> --from=A --to=B`**（`src/mergefidelity/parity.py`），
   让 6 个 parity fixture 的双向结果与 `expect.json` 的 `expect` / `expect_reverse` 逐项一致：
   - 候选集 `git rev-list --cherry-pick --right-only A...B`（注意：它用**默认上下文**的 cherry 判定，
     所以"跨行号/空白等价"的提交仍会留在候选里 —— 这正是 `-U0` 口径要补的那一类）；
   - A 侧 patch-id 索引用 `-U0`（`gitobj.commit_diff(..., context=0)` + `gitobj.patch_id`）；
   - 三态：`-U0` 相同 → `PRESENT(basis=patchid)`；否则在 **A 的临时 worktree** 上
     `apply --reverse --check`（`-U3`）→ `PRESENT(basis=apply)`；`apply --check` 成功 → `MISSING`；皆失败 → `MODIFIED`；
   - `note=content_equivalent_at_other_path`：同内容落在别的路径 → **只提示，不改判定**（path-remap 仍是 `MISSING`）；
   - `--no-apply-fallback`：不创建任何 worktree，只给 `PRESENT`/`MISSING`；
   - `patch_parity = present / total`，分母 0 → `null`。
2. **临时 worktree 纪律**：`gitobj.temporary_worktree()` 已实现（系统临时目录 + `try/finally` 三连清理）；
   报告里不得出现该绝对路径；测试要在**成功与异常两条路径**后断 `git worktree list` 无残留。
3. `tests/test_parity.py`：双向 golden 对账 + 三态齐 + `basis` 断言 + worktree 零残留 + `--no-apply-fallback`。
4. 退役 `parity` 骨架态（`parity.py` + 骨架登记测试 + `test_cli.py` 的 not-ready 参数）。
5. `tools/bench_parity.py` → `bench/parity.json`（候选数 / apply 兜底次数 / 耗时）。
6. 收尾：DoD 验证 → 回写 `plan/00`/`plan/05`/`plan/06` → 写 `plan/HANDOFF-M4.md` → commit。

## 3. 既定口径清单（K1–K24 见前两份 HANDOFF，本棒新增 K25–K30）

| # | 口径 | 落点 |
|---|---|---|
| K25 | **apply 兜底的 worktree 挂 A（源侧）**；挂 B 侧会恒成功、三态退化 | `data/README.md` §4.4、`plan/03` §2.2 |
| K26 | **patch-id 用 `-U0`（等价），apply 检查用 `-U3`（存在性）** | 同上；`gitobj.commit_diff(context=...)` |
| K27 | `note` **只提示不改判定**（`content_equivalent_at_other_path`）；`status` 由定义式决定 | `data/README.md` §4.4、golden |
| K28 | 三态优先级固定：`patchid` → `apply --reverse` → `apply` → `MODIFIED`；`basis` 字段必填 | `plan/03` §2.2 |
| K29 | `patch_parity` 分母 0 → `null`（不记 1.0） | `data/README.md` §4.4 |
| K30 | 临时 worktree **成功/异常两条路径都清理**（remove --force → prune → rmtree），报告不落绝对路径 | `gitobj.temporary_worktree` + 测试 |

## 4. 本机环境坑（2026-10-18 实测；引用前先复测）

- **`git diff-tree ... -- <path>` 的 `--` 必须在 revisions 之后**（否则 exit 129 用法错误）；
  `git diff <a> <b> -- <path>` 的 `--` 也在最后。根提交没有父提交 → patch-id 走 `--root`。
- **写入 `\x00` 这类转义极易踩坑**：本轮两次把真实 NUL/换行写进了源码（一次让文件无法 import）。
  需要 NUL 用 `chr(0)`，需要 LF 用模块级 `LF = chr(10)`（`diffparse.py` 已如此）。
- **Windows 上 git 对象只读 + 目录被占用**：删合成仓库要用生成器里的 `rmtree()`（先 `chmod`）；
  被进程占用的目录删不掉（`Device or resource busy`）——别把 shell 的 cwd 留在合成仓库里，
  迭代时换新的输出目录（`build/fx2`、`build/fx3`）即可，`build/` 不入仓。
- **`merge-tree --write-tree` 的对象隔离要"活着读到读完之后"**：`gitobj.MechanicalMerge` 是上下文管理器，
  机械树的 `ls-tree`/`diff` 必须传同一个 `env`；用完即删的 `merge_tree()` 只适合"只要 OID"的场景。
- fixture 每仓只有 1 个 merge，**性能斜率量不出来**：bench 另造 8-merge 合成仓（`--merges`）。
- 本机 pip 走系统代理 → `NO_PROXY="*"` + 清华镜像；`py -3.8 -m venv` 的 pip 20.2.3 不支持 `-e .`，先升 pip。

## 5. M2 的 DoD 逐项 checklist

- [x] `fidelity scan` 可用；12 个 fixture 的 payload 与 golden **逐项一致**（含 blob_fidelity 五个字段）
- [x] 三类 hunk 分类按 `data/README.md` §4.3 的单方向口径；每个注入 fixture 只报 1 处
- [x] 反例（`clean-resolution-a/b`、`drop-then-readd`、`custom-driver`）零 SMUGGLED / 零 DROPPED
- [x] octopus 与 custom_driver 显式 `SKIPPED`、不进分母、退出码 0
- [x] 同机双跑逐字节一致；`digest` 可复算；报告 0 绝对路径、`as_of` 不读时钟
- [x] `--fail-on` 三态退出码（命中 1 / 不命中 0）锁进测试
- [x] `bench/fidelity.json` 产出（含"批量 vs 逐进程"斜率与外环境样本量说明）
- [x] 骨架态退役同轮完成（代码 + 登记测试 + CLI 参数三处同步）
- [x] CI 新增可执行冒烟（`fidelity scan --fail-on=smuggled` 断言退出码 1），workflow 本地解析通过
- [ ] **CI 绿** —— 未接远端，**写"本地等价校验（待首推验证）"**，M6 首推后据实补记 run id

## 6. 关键命令速查

```bash
# fidelity 冒烟（fixture 仓库由生成器产出，不入仓）
py -3.8 tools/gen_fixtures.py --out data/fixtures --suite fidelity
PYTHONPATH=src py -3.8 -m mergefidelity fidelity scan data/fixtures/fidelity/smuggle-extra-line/repo
PYTHONPATH=src py -3.8 -m mergefidelity fidelity scan data/fixtures/fidelity/drop-one-side/repo --fail-on=dropped; echo "rc=$?"

# 测试
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m "not slow"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m slow
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest -q -m "not slow"

# 基准
py -3.8 tools/bench_fidelity.py --out bench/fidelity.json --repeats 3 --merges 8
```
