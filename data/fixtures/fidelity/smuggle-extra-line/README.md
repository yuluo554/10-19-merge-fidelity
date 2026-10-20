# fixture · fidelity / smuggle-extra-line

解冲突时在无关函数 helper() 里多加一行 `value += 1`（两侧父提交都没有它）

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only smuggle-extra-line
cd data/fixtures/fidelity/smuggle-extra-line/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["SMUGGLED","RESOLUTION"],"merges":[{"counts":{"dropped":0,"resolution":1,"smuggled":1},"hunks":[{"kind":"SMUGGLED","new_range":"7,1","old_range":"-","path":"src/synthapp/core.py"}],"mechanical_conflict":true,"mechanical_tree":"51683564511b1d935ddc0160f2ec776f5ec43045","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"8913b090e6af0e90a24bdca6ca6fe9d0ff994592","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","86cda620ea3d027281b036ac82d98fb886c78f92"],"recorded_tree":"034a628574b1cb6d8d4247c40d7e0e940461a259"}],"skipped":[]}
```
