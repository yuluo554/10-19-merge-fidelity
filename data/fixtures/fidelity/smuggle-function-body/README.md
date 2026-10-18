# fixture · fidelity / smuggle-function-body

解冲突时把 helper() 的倍率从 2 改成 3（两侧父提交都是 2）

## 手工复现

```bash
py -3.8 tools/gen_fixtures.py --out data/fixtures --only smuggle-function-body
cd data/fixtures/fidelity/smuggle-function-body/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["SMUGGLED","RESOLUTION"],"merges":[{"counts":{"dropped":0,"resolution":1,"smuggled":1},"hunks":[{"kind":"SMUGGLED","new_range":"6,1","old_range":"10,1","path":"src/synthapp/core.py"}],"mechanical_conflict":true,"mechanical_tree":"51683564511b1d935ddc0160f2ec776f5ec43045","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"137c087eea86682fa1ecf81580276ded20f8337b","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","86cda620ea3d027281b036ac82d98fb886c78f92"],"recorded_tree":"9f5c9cafdfa551feb4d08fdd6f654875d095eb91"}],"skipped":[]}
```
