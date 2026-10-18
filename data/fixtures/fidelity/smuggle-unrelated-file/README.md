# fixture · fidelity / smuggle-unrelated-file

解冲突时顺手改了与冲突无关的 src/synthapp/util.py（两侧父提交都没改它）

## 手工复现

```bash
py -3.8 tools/gen_fixtures.py --out data/fixtures --only smuggle-unrelated-file
cd data/fixtures/fidelity/smuggle-unrelated-file/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["SMUGGLED","RESOLUTION"],"merges":[{"counts":{"dropped":0,"resolution":1,"smuggled":1},"hunks":[{"kind":"SMUGGLED","new_range":"1,1","old_range":"1,1","path":"src/synthapp/util.py"}],"mechanical_conflict":true,"mechanical_tree":"51683564511b1d935ddc0160f2ec776f5ec43045","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"1f01d97b0020ca1854d92d1fda815b2818515954","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","86cda620ea3d027281b036ac82d98fb886c78f92"],"recorded_tree":"d7e032baf5b3da360c153f283cd9f5bec9afec1d"}],"skipped":[]}
```
