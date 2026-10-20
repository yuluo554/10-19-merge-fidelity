# fixture · fidelity / drop-one-side

解冲突时把一侧新增的 added_by_side() 整段丢掉（后续提交没有补回）

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only drop-one-side
cd data/fixtures/fidelity/drop-one-side/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["DROPPED","RESOLUTION"],"merges":[{"counts":{"dropped":1,"resolution":2,"smuggled":0},"hunks":[{"kind":"DROPPED","new_range":"-","old_range":"18,4","path":"src/synthapp/core.py"}],"mechanical_conflict":true,"mechanical_tree":"35b8796afb7bc1c87a0166c2ad8fb54725f0e8df","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"d81ab497dc437fdc7fa65a81263e6991c45f1732","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","caa0cf9960041d365417e3511269b3ddb2a2f55c"],"recorded_tree":"57fdf5f74cb199ecc182b799a1ac33606f3cda53"}],"skipped":[]}
```
