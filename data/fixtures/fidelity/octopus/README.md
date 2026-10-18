# fixture · fidelity / octopus

三父 octopus merge——必须输出 SKIPPED(reason=octopus) 且不影响退出码

## 手工复现

```bash
py -3.8 tools/gen_fixtures.py --out data/fixtures --only octopus
cd data/fixtures/fidelity/octopus/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["OCTOPUS"],"merges":[],"skipped":[{"merge_oid":"d8fa8a4a2eb92cb6f1287bdc59fa846a09442c5e","reason":"octopus"}]}
```
