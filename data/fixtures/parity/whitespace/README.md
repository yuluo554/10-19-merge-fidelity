# fixture · parity / whitespace

同一改动的空白形态不同——`-U0` patch-id 相同 → PRESENT

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only whitespace
cd data/fixtures/parity/whitespace/repo
git rev-list --cherry-pick --right-only release/1.0...main
```

## 期望（golden 摘要）

```json
{"candidates":2,"from":"release/1.0","missing":1,"modified":0,"present":1,"statuses":[["fix loose spacing","PRESENT"],["docs padding","MISSING"]],"to":"main"}
```
