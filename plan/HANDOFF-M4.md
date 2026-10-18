# HANDOFF-M4 · 下一棒：`ledger`（revert / 复活账本）

> 本文件由 M3 收尾时写入。上游：`plan/05-里程碑.md` 的 M4 行、`plan/03-模块详设.md` §3、`data/README.md` §4.5。
> 用法：新对话 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务`。

## 1. 当前进度与证据（M3 已完成）

| 项 | 状态 | 证据（2026-10-18 实测） |
|---|---|---|
| `parity` 实现 | ✅ | `src/mergefidelity/parity.py`：候选集 `--cherry-pick --right-only` → A 侧 `-U0` patch-id 索引 → 三态（`patchid` → `apply --reverse` → `apply` → `MODIFIED`）→ `note` 只提示不改判定 → `--no-apply-fallback` |
| golden 逐项一致 | ✅ | **6/6** parity fixture ×**双向**×逐候选 7 字段（`tests/test_parity.py`，参数化逐 fixture + 逐字段 + 9 个标量） |
| 候选顺序 | ✅ | 与 `git rev-list --cherry-pick --right-only A...B` 逐条同序（golden 同源），不引入额外排序口径 |
| 行号/空白等价 | ✅ | `context-shift`（第 2 行 vs 第 6 行）与 `whitespace`（`value=1` vs `value =    1`）均 `PRESENT(basis=patchid)` |
| 三态 + `basis` | ✅ | `bidirectional-basic` 一个方向即三态齐；每行 `basis ∈ {patchid, apply}` 必填 |
| `note` 不改判定 | ✅ | `path-remap` 断言 `status=MISSING` 且 `note=content_equivalent_at_other_path`（`equivalent_source` 指向 A 侧同内容提交） |
| worktree 纪律 | ✅ | 成功与人为异常两条路径后 `git worktree list` 只剩主工作树；`--no-apply-fallback` **零 worktree**；报告 0 绝对路径 |
| 骨架态退役 | ✅ | `parity.py` 的 `NotReadyError` 已删；骨架登记测试只剩 ledger/report/gate；`test_cli.py` 的 not-ready 参数同步缩小 |
| 基准 | ✅ | `bench/parity.json`：6 fixture 端到端 + `--no-apply-fallback` 对比（量化临时 worktree 固定开销） |
| CI 接线 | ✅ | 新增 step `CLI smoke (parity on generated fixtures)`（`set +e` + 断言退出码 0 + 断言 `candidates=4/present=1`）；workflow 本地 `yaml.safe_load` 通过（8 step） |
| 输入类错误归 2 | ✅ | 解不出来的 `--from/--to` → `UsageError`（退出码 2），不是 3（K31 落地） |
| 测试规模 | ✅ | 快层 **169 passed** ×（3.8 / 3.12）；慢层（`--check` 重生成 21 个仓库）1 passed |

**本地等价校验（未接远端，CI 待首推验证）**：双解释器快层、3.8 慢层、`--check` CLI 实跑、workflow 本地解析、parity CLI 冒烟。
**不可本机实跑**：Linux/macOS 的 `git apply`/`worktree` 行为差异（首份跨平台证据仍由 CI 首推给出）。

## 2. 下一棒待办（M4 = ledger）

1. **实现 `mergefidelity ledger <repo> [--range=REV|A..B]`**（`src/mergefidelity/ledger.py`），
   让 3 个 ledger fixture 与 `expect.json` 的 `entries` / `counts` / `unavailable` 逐项一致：
   - 枚举：`git log --grep='^This reverts commit' --format=%H<US>%B --all`（**正文**提取，不解析 subject）；
   - 被回滚 OID：正则 `^This reverts commit ([0-9a-f]{7,64})`（`re.MULTILINE`），`rev-parse --verify <oid>^{commit}`；
   - **校验**：revert commit 的 `U0_patchid` vs 被回滚 commit 的 diff **取反**后的 `U0_patchid`；
     不等 → `REVERT_UNVERIFIED`（`verified=false`，**不猜意图**，不算 successor）；
   - **重放**：`U0_patchid` 与原始相等即在 revert 之后的提交里找 successor
     （oracle 用 `_commits_after`；`--find-object=<blob> --all` 是更省的候选筛选，但**结论口径以 patch-id 相等为准**）；
     找到 → `REVERTED_THEN_REDONE(successor_oid=…)`；找不到 → `REVERTED_NO_SUCCESSOR`；
   - 排序 `(被回滚 commit_time, revert_oid)`；同一 revert 只入账一次；
   - `counts` 三键 + `unavailable`（`--find-object` 不支持时 `UNAVAILABLE(reason=git_too_old)`，**不降级猜**）。
2. `tests/test_ledger.py`：三状态各一 fixture 逐字段 + `patchid-mismatch` 断言 `REVERT_UNVERIFIED` +
   `UNAVAILABLE` 与"无 successor"是不同输出 + 确定性（双跑一致 / digest 可复算）。
3. 退役 `ledger` 骨架态（`ledger.py` + 骨架登记测试 + `test_cli.py` 的 not-ready 参数**三处同步**）。
4. `tools/bench_ledger.py` → `bench/ledger.json`（条目数 / 耗时）。
5. 收尾：DoD 验证 → 回写 `plan/00`/`plan/03`/`plan/04`/`plan/05`/`plan/06`/README → 写 `plan/HANDOFF-M5.md` → commit。

## 3. 既定口径清单（K1–K31 见前几份 HANDOFF，本棒新增 K32–K36）

| # | 口径 | 落点 |
|---|---|---|
| K32 | **`parity` 候选顺序取 `git rev-list` 原序**（`plan/03` §2.2 原写"(commit_time, oid) 排序"是笔误） | `parity.parity_scan`、golden、`plan/00` 决策记录表 |
| K33 | **`note` 与 `status` 解耦**：`equivalent_source` 在 `PRESENT` 时指同 patch-id 提交，在跨路径提示时指同内容提交 | `data/README.md` §4.4、`plan/00` 决策记录表、`test_parity.py` |
| K34 | **`--no-apply-fallback` 下 patch-id 不等 → `MODIFIED(basis=patchid)`**（没有 apply 证据就不声称"缺失"）。**本棒按 `plan/03` §2.2 的"第三态标 MODIFIED"落地，取代 `HANDOFF-M3` 待办第 1 条里"只给 PRESENT/MISSING"的简写**——那两句互相矛盾，已统一并在 `plan/00` 决策记录表留痕 | `plan/03` §2.2、README「已知边界」、`test_parity.py` |
| K35 | **`--from/--to` 解不出来 → 退出码 2**（输入类错误，不是环境类；照 K31 办理） | `parity._resolve_refs`（复用 `fidelity.require_ref`）、`test_parity.py` |
| K36 | **临时 worktree per invocation 只创建一次**；`worktree: {created, reason}` 进报告（**路径不进报告**）；无候选时不创建 | `parity.parity_scan`、`test_parity.py` |

## 4. 本机环境坑（2026-10-18 实测；引用前先复测）

- **`git rev-list --cherry-pick --right-only A...B` 的顺序就是 golden 的顺序**：不要"顺手"再排一次序
  ——多一层排序口径 = 多一个 golden 对不上的点。`git cherry -v A B` 的候选条数与之相同，只作交叉核对。
- **`git apply` 的 `--check` 不写文件、但需要工作区**：临时 worktree 用 `git worktree add --detach`
  挂在**源侧 A**；`git -C <worktree> apply --check` 才能读到那棵工作树。挂 B 侧会恒成功。
- **`mkdtemp` 建出的目录不能直接给 `git worktree add`**（非空检测）：先 `os.rmdir` 再让 git 建
  （`gitobj.temporary_worktree` 已如此）。
- **Windows 上 worktree 目录可能一时删不掉**（`Device or resource busy`）：清理走
  `worktree remove --force` → `worktree prune` → `shutil.rmtree(ignore_errors=True)` 三连。
- **`--no-renames` 的两份实现不一致是有意的**：oracle 的 `commit_diff_text` 默认带 rename 检测，
  生产 `gitobj.commit_diff` 固定 `--no-renames`。fixture 无 rename，结论一致；改 fixture 时要留意。
- **不要用 `python`**：本机 `python` 可能是商店占位符，一律 `py -3.8` / `py -3.12` 并加 `-X utf8`。
- 本机 pip 走系统代理 → `NO_PROXY="*"` + 清华镜像；`py -3.8 -m venv` 的 pip 20.2.3 不支持 `-e .`，先升 pip。

## 5. M3 的 DoD 逐项 checklist

- [x] `parity --from=A --to=B` 可用；6 个 fixture 的**双向**结果与 golden **逐项一致**（含 `basis`/`note`/`equivalent_source`/`paths`）
- [x] 三态定义式落地：`patchid` → `apply --reverse` → `apply` → `MODIFIED`；`basis` 字段必填
- [x] `-U0` 跨行号（`context-shift`）与空白（`whitespace`）等价 → `PRESENT(basis=patchid)`
- [x] `path-remap` 的 `note` 只提示不改判定（仍是 `MISSING`）
- [x] 临时 worktree 成功/异常两条路径后 `git worktree list` 无残留；`--no-apply-fallback` 不创建 worktree
- [x] `patch_parity` 与 `present/candidates` 一致；分母 0 → `null`
- [x] 同机双跑逐字节一致；`digest` 可复算；报告 0 绝对路径；`as_of` 不读时钟
- [x] 输入类错误（坏 `--from/--to`）→ 退出码 2
- [x] `bench/parity.json` 产出（含与无兜底的耗时对比）
- [x] 骨架态退役同轮完成（代码 + 登记测试 + CLI 参数三处同步）
- [x] CI 新增 parity 冒烟（断言退出码 0 + `candidates=4/present=1`），workflow 本地解析通过
- [ ] **CI 绿** —— 未接远端，**写"本地等价校验（待首推验证）"**，M6 首推后据实补记 run id

## 6. 关键命令速查

```bash
# parity 冒烟（fixture 仓库由生成器产出，不入仓）
py -3.8 tools/gen_fixtures.py --out data/fixtures --suite parity
PYTHONPATH=src py -3.8 -m mergefidelity parity data/fixtures/parity/bidirectional-basic/repo \
    --from=release/1.0 --to=main          # rc=0；candidates=4 / present=1 / missing=2 / modified=1
PYTHONPATH=src py -3.8 -m mergefidelity parity data/fixtures/parity/whitespace/repo \
    --from=release/1.0 --to=main --no-apply-fallback   # 不建临时 worktree

# 测试
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m "not slow"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m slow
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest -q -m "not slow"

# 基准
py -3.8 tools/bench_parity.py --out bench/parity.json --repeats 3
```
