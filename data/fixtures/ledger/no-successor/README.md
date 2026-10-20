# fixture · ledger / no-successor

回滚后没有任何后续提交重新引入该改动 → REVERTED_NO_SUCCESSOR

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only no-successor
cd data/fixtures/ledger/no-successor/repo
git log --grep='^This reverts commit' --format='%H%x00%B' | cat
```

## 期望（golden 摘要）

```json
{"counts":{"no_successor":1,"then_redone":0,"unverified":0},"injects":["REVERTED_NO_SUCCESSOR"]}
```
