# fixture · parity / bidirectional-basic

双向：release/1.0 与 main 上的修复互相对齐（PRESENT/MODIFIED/MISSING 三态齐）

## 手工复现

```bash
py -3.8 tools/gen_fixtures.py --out data/fixtures --only bidirectional-basic
cd data/fixtures/parity/bidirectional-basic/repo
git rev-list --cherry-pick --right-only release/1.0...main
```

## 期望（golden 摘要）

```json
{"candidates":4,"from":"release/1.0","missing":2,"modified":1,"present":1,"statuses":[["new api","MISSING"],["variant of fix B","MODIFIED"],["fix A on main","PRESENT"],["docs padding","MISSING"]],"to":"main"}
```
