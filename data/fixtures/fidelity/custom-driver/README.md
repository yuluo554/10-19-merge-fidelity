# fixture · fidelity / custom-driver

`synthapp.dat` 命中自定义 merge driver：该路径必须 SKIPPED(reason=custom_driver) 且不进 blob_fidelity 分母

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only custom-driver
cd data/fixtures/fidelity/custom-driver/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["CUSTOM_DRIVER"],"merges":[{"counts":{"dropped":0,"resolution":1,"smuggled":0},"hunks":[],"mechanical_conflict":true,"mechanical_tree":"22c5c6e56c17340e6d348bc09e9cec9754e1a97a","merge_base":"c07a65611c822dd54e10a60ee40d95589cb51afe","merge_oid":"484855a5f6cbe9195db466214a78d5bf748b7385","parents":["3685c3891f1da3cdf49b6e9c810e5a115e1947c2","0a0312311ff8b329368ce631d140edc799b83cdf"],"recorded_tree":"63230adbbe9e7706533b9b9d13c8ed128de2919c"}],"skipped":[{"merge_oid":"484855a5f6cbe9195db466214a78d5bf748b7385","paths":["synthapp.dat"],"reason":"custom_driver"}]}
```
