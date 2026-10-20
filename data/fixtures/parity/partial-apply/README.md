# fixture · parity / partial-apply

目标侧只含一半改动——两个方向的 apply 检查都失败 → MODIFIED

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only partial-apply
cd data/fixtures/parity/partial-apply/repo
git rev-list --cherry-pick --right-only release/1.0...main
```

## 期望（golden 摘要）

```json
{"candidates":2,"from":"release/1.0","missing":1,"modified":1,"present":0,"statuses":[["whole fix","MODIFIED"],["docs padding","MISSING"]],"to":"main"}
```
