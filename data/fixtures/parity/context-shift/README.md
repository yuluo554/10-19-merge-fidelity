# fixture · parity / context-shift

同一改动落在不同行号、上下文不同——`-U0` patch-id 相同 → PRESENT

## 手工复现

```bash
py -3.8 tools/gen_fixtures.py --out data/fixtures --only context-shift
cd data/fixtures/parity/context-shift/repo
git rev-list --cherry-pick --right-only release/1.0...main
```

## 期望（golden 摘要）

```json
{"candidates":2,"from":"release/1.0","missing":1,"modified":0,"present":1,"statuses":[["fix at line 6","PRESENT"],["docs padding","MISSING"]],"to":"main"}
```
