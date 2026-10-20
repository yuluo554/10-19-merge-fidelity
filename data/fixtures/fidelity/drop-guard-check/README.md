# fixture · fidelity / drop-guard-check

解冲突时删掉了 guard() 的负数校验（两侧父提交都保留了它）

## 手工复现

```bash
py -3.12 tools/gen_fixtures.py --out data/fixtures --only drop-guard-check
cd data/fixtures/fidelity/drop-guard-check/repo
git log --oneline --graph | cat
git log --merges --remerge-diff -p --no-renames --format='%H%x00%P' | cat
```

## 期望（golden 摘要）

```json
{"injects":["DROPPED","RESOLUTION"],"merges":[{"counts":{"dropped":1,"resolution":1,"smuggled":0},"hunks":[{"kind":"DROPPED","new_range":"-","old_range":"15,2","path":"src/synthapp/core.py"}],"mechanical_conflict":true,"mechanical_tree":"51683564511b1d935ddc0160f2ec776f5ec43045","merge_base":"714c1066e559b5f10451d7ca65c9f4bcceb01864","merge_oid":"e746986ac990281aa876fe8bd7e7aceda78cf366","parents":["ea8790e655d2df96ab0f58cb51ac235a778c1da4","86cda620ea3d027281b036ac82d98fb886c78f92"],"recorded_tree":"1a9337f4266443230fb6002c6c42082c41db458f"}],"skipped":[]}
```
