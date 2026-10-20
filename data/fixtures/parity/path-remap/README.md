# fixture · parity / path-remap

同内容换到另一个路径——patch-id 因路径不同而不同，apply 也失败 → MODIFIED

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only path-remap
cd data/fixtures/parity/path-remap/repo
git rev-list --cherry-pick --right-only release/1.0...main
```

## 期望（golden 摘要）

```json
{"candidates":2,"from":"release/1.0","missing":2,"modified":0,"present":0,"statuses":[["same fix elsewhere","MISSING"],["docs padding","MISSING"]],"to":"main"}
```
