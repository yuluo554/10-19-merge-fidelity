# HANDOFF-M2 · 下一棒：`fidelity scan`（Merge 保真度扫描）

> 本文件由 M1 收尾时写入。上游：`plan/05-里程碑.md` 的 M2 行、`data/README.md` §4.1–§4.3。
> 用法：新对话 `/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务`。

## 1. 当前进度与证据（M1 已完成）

| 项 | 状态 | 证据（2026-10-18 实测） |
|---|---|---|
| 生成器 `tools/gen_fixtures.py` | ✅ | 零依赖、不 import `mergefidelity`；`--out / --only / --suite / --check` 四种用法 |
| fixture 规模 | ✅ | **20** = fidelity **11** · parity **6** · ledger **3**（`data/fixtures/manifest.json` 与目录双向一致，有测试） |
| 位级一致守门 | ✅ | `py -3.8 tools/gen_fixtures.py --out data/fixtures --check` → `--check 通过：20 个 fixture 与冻结产物逐字节一致`（exit 0）；`tests/test_gen_fixtures.py::test_check_regenerates_byte_identical_from_frozen`（`slow`）复证 |
| 植入器自证 | ✅ | 每个 fidelity fixture 的**声明计数**在**生成期**与 oracle 复算逐项对账（`_validate_declared`），不符即 `GenError` |
| 反例在列 | ✅ | `clean-resolution-a/b`、`drop-then-readd` 断言 `smuggled=0 且 dropped=0` |
| 三态/账本 golden | ✅ | parity 双向覆盖 `PRESENT(patchid)`/`MISSING`/`MODIFIED`；ledger 三状态各一 |
| 入仓分层 | ✅ | 仓库本体在 `data/fixtures/**/repo/`（`.gitignore` 排除，有测试断言 `git check-ignore` 命中）；入仓的是生成器 + `expect.json` + 每例 `README.md` + `manifest.json` |
| 测试 | ✅ | 快层 **87 passed**（3.8 与 3.12 各一遍，`-m "not slow"`）；慢层 **1 passed**（3.8 实跑 `--check`） |

**本地等价校验（未接远端，CI 待首推验证）**：双解释器快层全量、3.8 慢层实跑、
`--check` CLI 形式实跑。**不可本机实跑**：Linux/macOS 行为差异、GitHub runner 的编码与路径形态。

## 2. 下一棒待办（M2 = fidelity 模块）

1. **实现 `mergefidelity fidelity scan`**（`src/mergefidelity/fidelity.py`），
   让 11 个 fidelity fixture 的输出与 `expect.json` 逐项一致：
   - 枚举 `rev-list --merges --reverse --topo-order`；
   - 单进程 `git log --merges --remerge-diff -p --no-renames --format=%H%x00%P` 拿全量 payload；
   - 对 payload 非空的 merge 用 `gitobj.merge_tree()`（已带对象隔离）复算机械树并逐 blob 比较；
   - hunk 三分按 **`data/README.md` §4.3 的单方向口径**（golden 就是这么算的）：
     `git diff -U0 <mechanical_tree> <recorded_tree>`，含冲突标记 → RESOLUTION，含 `+` → SMUGGLED，
     只含 `-` → DROPPED 候选（再过同路径 `-U0` patch-id 的"是否被重新引入"）；
   - 交叉校验：payload 路径与树 diff 路径不一致时报 `CROSSCHECK_MISMATCH`，不静默取其一；
   - `octopus` 用**父提交数 >2** 判定（不解析 stderr），不进 `blob_fidelity` 分母，退出码不受影响。
2. **比对口径**：golden 比的是**报告 payload**（`merges[*]` / `skipped[*]` / `counts` / `blob_fidelity`），
   不是整份报告——报告头含 `git_version`，跨机不可比。报告自身的确定性另有"同机双跑逐字节一致"兜底。
3. **补 2 件 M1 顺延项**：
   - `custom-driver` fixture（`.gitattributes` 指定自定义 merge driver，driver 命令要跨平台可用）
     + `SKIPPED(reason=custom_driver)` 判定，**同步落地**；
   - `tests/test_fidelity.py`：golden 逐项对账 + 双跑一致 + `--fail-on=smuggled` 退出码 + octopus 退出码 0。
4. **退役骨架态**：删掉 `fidelity.py` 的 `NotReadyError`，同步缩小
   `tests/test_readme_gate.py::test_skeleton_not_ready_registry_is_explicit`。
5. `tools/bench_fidelity.py` → `bench/fidelity.json`（样本量与环境如实标注，性能数字**不写进断言**）。
6. 收尾：DoD 验证 → 回写 `plan/00`/`plan/05`/`plan/06` → 写 `plan/HANDOFF-M3.md` → commit。

## 3. 既定口径清单（K1–K15 见 `plan/HANDOFF-M1.md`，本棒新增 K16–K24）

| # | 口径 | 落点 |
|---|---|---|
| K16 | **hunk 分类只用一个方向**：`git diff -U0 <mechanical> <recorded>`；含冲突标记 → RESOLUTION，含 `+` → SMUGGLED，只含 `-` → DROPPED | `data/README.md` §4.3、生成器 oracle、M2 实现 |
| K17 | **"删掉内容"= DROPPED**（不是 SMUGGLED）；`smuggle-delete-guard` 已改名 `drop-guard-check` | `plan/04` 表、golden |
| K18 | **parity 的 apply 兜底挂 A（源侧）**；patch-id 用 `-U0`（等价），apply 用 `-U3`（存在性） | `data/README.md` §4.4、`plan/03` §2.2 |
| K19 | `path-remap` 判 **MISSING** + `note=content_equivalent_at_other_path`（note 只提示不改判定） | `data/README.md` §4.4、golden |
| K20 | `RESOLUTION` 是 **hunk 粒度**：一个冲突区可能因 `-U0` 切成多个（实测 `drop-one-side` = 2） | `data/README.md` §4.3 |
| K21 | golden = **payload 级**比较（不含报告头）；`--check` = 重生成逐字节 + 逐文件比对 | `plan/04` §六、`tests/test_gen_fixtures.py` |
| K22 | 合成仓库本体**不入仓**且必须被 `.gitignore` 命中（有测试）；`manifest.json` 是生成物 | `.gitignore`、`tests/test_gen_fixtures.py` |
| K23 | 生成期**声明自证**：fixture 的 `declared_counts` 必须等于 oracle 复算，不符即 `GenError` | `tools/gen_fixtures.py::_validate_declared` |
| K24 | `merge-tree` 的对象隔离**必须**：`TempObjects` 且目标对象目录预先 `makedirs`；oracle 读机械树时**同一 env 传下去** | `tools/gen_fixtures.py`、`src/mergefidelity/gitobj.py` |

## 4. 本机环境坑（2026-10-18 实测；引用前先复测）

- `py -0p` → 3.8.8-64 与 3.12.10；pytest 7.4.4 / 8.4.2；PyYAML 6.0.3；git 2.54.0.windows.1。
- **`py -3.8 -m venv` 的 pip 是 20.2.3** → `pip install -e .` 报 "editable mode currently requires a
  setup.py based build"；先 `python -m pip install -U pip`（CI 第一条 pip 步骤已含）。setuptools 75.3.4 可用。
- pip 走系统代理会 `ProxyError`：`NO_PROXY="*" no_proxy="*" ... -i https://pypi.tuna.tsinghua.edu.cn/simple`。
- **Windows 上 git 对象是只读**：`shutil.rmtree` 删合成仓库会 `PermissionError`——生成器里有
  `rmtree()`（先 `chmod` 再删，3.8 走 `onerror`、3.12 走 `onexc`）。**已被某进程占用的目录删不掉**
  （`Device or resource busy`）：别把 shell 的 cwd 留在合成仓库里（本机实测踩到一次，
  换成新输出目录继续即可，产物目录在 `.gitignore` 内）。
- **`git diff-tree ... -- <path>` 的 `--` 必须排在 revisions 之后**，否则 git 报用法错误（exit 129）；
  同类：`git diff <a> <b> -- <path>` 的 `--` 也在最后。
- **根提交没有父提交**：`<c>^` 会 `unknown revision`；patch-id 复算要走 `--root`（取反无意义 → 返回 `None`）。
- 探针命令的 `&&` 链可能在 `cd` 失败时不中断而落在上一个目录（M0 实录：凭空建了 `other` 分支）；
  探针一律用绝对路径、事后 `git branch -v` + `git reflog` 核对。

## 5. M1 的 DoD 逐项 checklist

- [x] 生成器可重建 20 个 fixture（fidelity 11 / parity 6 / ledger 3），全部确定性（固定作者/时间/内容/分支）
- [x] `--check` 位级一致（CLI 实跑 exit 0 + `slow` 测试复证）
- [x] 每个 fidelity fixture 只注入 1 处缺陷，且**生成期**与声明对账
- [x] 反例在列：`clean-resolution-a/b`、`drop-then-readd` 均断言零 SMUGGLED / 零 DROPPED
- [x] octopus fixture 产出 `SKIPPED(reason=octopus)` 且不进 `blob_fidelity` 分母
- [x] parity 双向三态齐 + `-U0` 跨行号/空白等价的 PRESENT 证据（`basis=patchid`）
- [x] ledger 三状态各一，`REVERT_UNVERIFIED` 与"无 successor"是两种结论
- [x] golden 为规范 JSON + LF（有测试）；`manifest.json` 与目录内容一致（有测试）
- [x] 合成仓库不入仓且确实被 ignore（有测试）
- [x] 口径勘误回写三处（`data/README.md` §4.3/§4.4、`plan/03`、`plan/04`）+ 决策记录 7 条（`plan/00`）
- [ ] **CI 绿** —— 未接远端，**写"本地等价校验（待首推验证）"**，M6 首推后据实补记 run id
- [ ] `custom-driver` fixture —— **顺延到 M2**（与 `SKIPPED(custom_driver)` 判定同步落地），如实计入 M2 待办

**M2 收尾补记（追加事实，不改上文原文）**：`custom-driver` fixture 与 `SKIPPED(custom_driver)`
判定已在 M2 同轮落地（`.gitattributes` + `git merge-file --union` 作 driver），fidelity 现为 12 个 fixture；
上面这条「顺延」已闭环，见 `plan/HANDOFF-M3.md` §1/§5。

## 6. 关键命令速查

```bash
# 生成 / 复检（--check 会重生成 20 个仓库，约 45 s）
py -3.8 tools/gen_fixtures.py --out data/fixtures
py -3.8 tools/gen_fixtures.py --out data/fixtures --check
py -3.8 tools/gen_fixtures.py --out build/fx --only drop-one-side --suite fidelity

# 测试
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m "not slow"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.8 -X utf8 -m pytest -q -m slow
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src py -3.12 -X utf8 -m pytest -q -m "not slow"

# 看一眼 golden
py -3.8 -c "import io,json;print(json.dumps(json.load(io.open('data/fixtures/fidelity/drop-one-side/expect.json',encoding='utf-8'))['merges'],ensure_ascii=False,indent=1))"
```
