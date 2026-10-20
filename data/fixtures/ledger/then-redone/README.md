# fixture · ledger / then-redone

回滚后同一 patch 再次落地 → REVERTED_THEN_REDONE

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only then-redone
cd data/fixtures/ledger/then-redone/repo
git log --grep='^This reverts commit' --format='%H%x00%B' | cat
```

## 期望（golden 摘要）

```json
{"counts":{"no_successor":0,"then_redone":1,"unverified":0},"injects":["REVERTED_THEN_REDONE"]}
```
