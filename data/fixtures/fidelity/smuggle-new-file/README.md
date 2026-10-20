# fixture · fidelity / smuggle-new-file

解冲突时新增了一个两侧父提交都不存在的文件 docs/generated.md

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only smuggle-new-file
cd data/fixtures/fidelity/smuggle-new-file/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["SMUGGLED","RESOLUTION"],"merges":[{"counts":{"dropped":0,"resolution":1,"smuggled":1},"hunks":[{"kind":"SMUGGLED","new_range":"0,2","old_range":"-","path":"docs/generated.md"}],"mechanical_conflict":true,"mechanical_tree":"51683564511b1d935ddc0160f2ec776f5ec43045","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"0b999b0bc98290e0ab485d781d08ceef5118a614","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","86cda620ea3d027281b036ac82d98fb886c78f92"],"recorded_tree":"88082f44696fd34a7a6c64a5da7d60c11f7f805f"}],"skipped":[]}
```
