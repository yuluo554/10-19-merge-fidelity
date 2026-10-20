# fixture · ledger / patchid-mismatch

正文声称回滚 X、实际 diff 回滚 Y → REVERT_UNVERIFIED（不猜意图）

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only patchid-mismatch
cd data/fixtures/ledger/patchid-mismatch/repo
git log --grep='^This reverts commit' --format='%H%x00%B' | cat
```

## 期望（golden 摘要）

```json
{"counts":{"no_successor":0,"then_redone":0,"unverified":1},"injects":["REVERT_UNVERIFIED"]}
```
