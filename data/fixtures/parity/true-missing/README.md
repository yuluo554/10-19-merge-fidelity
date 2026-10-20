# fixture · parity / true-missing

目标侧完全没有该改动——`apply --check` 成功 → MISSING

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only true-missing
cd data/fixtures/parity/true-missing/repo
git rev-list --cherry-pick --right-only release/1.0...main
```

## 期望（golden 摘要）

```json
{"candidates":1,"from":"release/1.0","missing":1,"modified":0,"present":0,"statuses":[["brand new module","MISSING"]],"to":"main"}
```
