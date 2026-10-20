# fixture · fidelity / clean-resolution-a

两侧改动都保留（各占一行）——反例：不得报 SMUGGLED / DROPPED

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only clean-resolution-a
cd data/fixtures/fidelity/clean-resolution-a/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["CLEAN_RESOLUTION"],"merges":[{"counts":{"dropped":0,"resolution":2,"smuggled":0},"hunks":[],"mechanical_conflict":true,"mechanical_tree":"51683564511b1d935ddc0160f2ec776f5ec43045","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"fe73f11697f7433aa73834bb99b75abf55810938","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","86cda620ea3d027281b036ac82d98fb886c78f92"],"recorded_tree":"65197dc97a2f54bde24e5409a73e8ea243f001a5"}],"skipped":[]}
```
