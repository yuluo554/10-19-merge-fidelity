# fixture · fidelity / clean-resolution-b

把两侧改动语义合并成一行（x + 30）——反例：不得报 SMUGGLED / DROPPED

## 手工复现

```bash
py -3.8 tools/gen_fixtures.py --out data/fixtures --only clean-resolution-b
cd data/fixtures/fidelity/clean-resolution-b/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["CLEAN_RESOLUTION"],"merges":[{"counts":{"dropped":0,"resolution":1,"smuggled":0},"hunks":[],"mechanical_conflict":true,"mechanical_tree":"51683564511b1d935ddc0160f2ec776f5ec43045","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"8dc8f79219a42b097545b5511a7ac4a9f91197f0","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","86cda620ea3d027281b036ac82d98fb886c78f92"],"recorded_tree":"d24902564c3e876325c781814d37385f4afb9ebe"}],"skipped":[]}
```
