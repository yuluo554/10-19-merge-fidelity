# fixture · fidelity / drop-then-readd

解冲突时丢掉一侧新增的函数，**但后续提交原样补回**——不得报 DROPPED

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only drop-then-readd
cd data/fixtures/fidelity/drop-then-readd/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["DROPPED_THEN_RESTORED","RESOLUTION"],"merges":[{"counts":{"dropped":0,"resolution":2,"smuggled":0},"hunks":[],"mechanical_conflict":true,"mechanical_tree":"35b8796afb7bc1c87a0166c2ad8fb54725f0e8df","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"d81ab497dc437fdc7fa65a81263e6991c45f1732","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","caa0cf9960041d365417e3511269b3ddb2a2f55c"],"recorded_tree":"57fdf5f74cb199ecc182b799a1ac33606f3cda53"}],"skipped":[]}
```
