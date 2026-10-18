# fixture · fidelity / drop-partial-hunk

解冲突时只保留了新增函数的一部分（`b` 与 `return` 行被静默丢掉）

## 手工复现

```bash
py -3.8 tools/gen_fixtures.py --out data/fixtures --only drop-partial-hunk
cd data/fixtures/fidelity/drop-partial-hunk/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["DROPPED","RESOLUTION"],"merges":[{"counts":{"dropped":1,"resolution":2,"smuggled":0},"hunks":[{"kind":"DROPPED","new_range":"-","old_range":"22,2","path":"src/synthapp/core.py"}],"mechanical_conflict":true,"mechanical_tree":"713cf2caa708a9f8655bad319a6a7f3004fa3102","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"d7bd199246962b9693c03b1bc34354f597e900d1","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","6e9b466076ea393e83344b7fcc1824b7f7c0fc50"],"recorded_tree":"7491f1afea189b4c7f440770428721040284dcf8"}],"skipped":[]}
```
