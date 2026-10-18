"""git 访问层守门：版本门槛、只读性、对象隔离、worktree 清理、编码。"""

import os

import pytest

from mergefidelity import gitobj
from mergefidelity.errors import GitEnvError

import synthrepo


def _count_objects(repo):
    root = os.path.join(gitobj.git_dir(repo), "objects")
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        total += len(filenames)
    return total


def _clean_merge_repo(tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "r"))
    synthrepo.commit(repo, "base", {"f.txt": ["a", "b", "c"], "g.txt": ["x"]})
    synthrepo.git(repo, "checkout", "-q", "-b", "side")
    synthrepo.commit(repo, "side", {"g.txt": ["x", "side"]})
    synthrepo.git(repo, "checkout", "-q", "main")
    synthrepo.commit(repo, "main", {"f.txt": ["a", "b", "C-main"]})
    synthrepo.git(repo, "merge", "--no-edit", "side")
    return repo


def _conflict_merge_repo(tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "c"))
    synthrepo.commit(repo, "base", {"f.txt": ["a", "b", "c", "d", "e"]})
    synthrepo.git(repo, "checkout", "-q", "-b", "side")
    synthrepo.commit(repo, "side", {"f.txt": ["a", "B-side", "c", "d", "e"]})
    synthrepo.git(repo, "checkout", "-q", "main")
    synthrepo.commit(repo, "main", {"f.txt": ["a", "B-main", "c", "d", "e"]})
    synthrepo.git(repo, "merge", "--no-edit", "side", check=False)
    synthrepo.commit(repo, "resolve", {"f.txt": ["a", "B-resolved", "c", "d", "e"]})
    return repo


# ---------------------------------------------------------------- 版本

def test_parse_version_forms():
    assert gitobj.parse_version("git version 2.54.0.windows.1") == (2, 54, 0)
    assert gitobj.parse_version("git version 2.39.2\n") == (2, 39, 2)
    assert gitobj.parse_version("git version 2.36") == (2, 36, 0)


def test_parse_version_rejects_garbage():
    with pytest.raises(GitEnvError):
        gitobj.parse_version("not a version")


def test_require_version_passes_on_current_git(tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "v"))
    text = gitobj.require_version(repo, (2, 20))
    assert "git version" in text


def test_require_version_below_threshold_raises(tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "v2"))
    with pytest.raises(GitEnvError) as excinfo:
        gitobj.require_version(repo, (99, 0))
    assert "99.0" in str(excinfo.value)


def test_run_git_missing_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(gitobj, "GIT_EXECUTABLE", "no-such-git-binary")
    with pytest.raises(GitEnvError) as excinfo:
        gitobj.run_git(str(tmp_path), ["--version"])
    assert "not found" in str(excinfo.value)


def test_run_git_timeout(monkeypatch, tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "t"))
    with pytest.raises(GitEnvError) as excinfo:
        gitobj.run_git(repo, ["rev-parse", "HEAD"], timeout=0.0001)
    assert "timeout" in str(excinfo.value).lower()


def test_is_git_repo_and_require(tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "g"))
    assert gitobj.is_git_repo(repo) is True
    plain = tmp_path / "plain"
    plain.mkdir()
    assert gitobj.is_git_repo(str(plain)) is False
    with pytest.raises(GitEnvError):
        gitobj.require_git_repo(str(plain))
    with pytest.raises(GitEnvError):
        gitobj.require_git_repo(str(tmp_path / "does-not-exist"))


# ---------------------------------------------------------------- 对象读取

def test_blob_map_and_ls_tree_are_zero_quoted(tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "q"))
    synthrepo.commit(repo, "中文文件名", {"src/synthapp/模块.py": ["print(1)"]})
    blobs = gitobj.blob_map(repo, "HEAD")
    assert "src/synthapp/模块.py" in blobs
    entries = gitobj.ls_tree(repo, "HEAD")
    assert entries["src/synthapp/模块.py"][0] == "100644"


def test_blob_map_skips_non_blobs(tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "sub"))
    synthrepo.commit(repo, "tree", {"f.txt": ["x"]})
    blobs = gitobj.blob_map(repo, "HEAD")
    assert all(len(oid) == 40 or len(oid) == 64 for oid in blobs.values())


def test_commit_meta(tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "m"))
    oid = synthrepo.commit(repo, "主题：中文", {"f.txt": ["x"]})
    got_oid, parents, commit_time, subject = gitobj.commit_meta(repo, "HEAD")
    assert got_oid == oid
    assert parents == ()
    assert subject == "主题：中文"
    assert commit_time > 0


def test_attributes_oid_absent_and_present(tmp_path):
    repo = synthrepo.init_repo(str(tmp_path / "a"))
    synthrepo.commit(repo, "no attrs", {"f.txt": ["x"]})
    assert gitobj.attributes_oid(repo, "HEAD") is None
    synthrepo.commit(repo, "attrs", {"f.txt": ["x"], ".gitattributes": ["* text=auto"]})
    oid = gitobj.attributes_oid(repo, "HEAD")
    assert oid and len(oid) in (40, 64)


# ---------------------------------------------------------------- merge-tree

def test_merge_tree_clean_matches_recorded_tree(tmp_path):
    repo = _clean_merge_repo(tmp_path)
    merge = gitobj.rev_parse(repo, "HEAD")
    p1, p2 = gitobj.rev_parse(repo, "HEAD^1"), gitobj.rev_parse(repo, "HEAD^2")
    base = gitobj.rev_parse(repo, "HEAD^^")
    mechanical = gitobj.merge_tree(repo, base, p1, p2)
    assert mechanical.has_conflict is False
    assert mechanical.tree_oid == gitobj.rev_parse(repo, "HEAD^{tree}")
    assert mechanical.entries == ()


def test_merge_tree_does_not_write_repository_objects(tmp_path):
    repo = _conflict_merge_repo(tmp_path)
    before = _count_objects(repo)
    p1, p2 = gitobj.rev_parse(repo, "HEAD^1"), gitobj.rev_parse(repo, "HEAD^2")
    base = gitobj.rev_parse(repo, "HEAD^^")
    result = gitobj.merge_tree(repo, base, p1, p2)
    after = _count_objects(repo)
    assert after == before, "merge-tree 不得向仓库对象库写入任何对象"
    assert result.has_conflict is True or result.tree_oid


def test_merge_tree_conflict_entries_have_three_stages(tmp_path):
    repo = _conflict_merge_repo(tmp_path)
    p1, p2 = gitobj.rev_parse(repo, "HEAD^1"), gitobj.rev_parse(repo, "HEAD^2")
    base = gitobj.rev_parse(repo, "HEAD^^")
    mechanical = gitobj.merge_tree(repo, base, p1, p2)
    stages = sorted(entry["stage"] for entry in mechanical.entries)
    assert stages == [1, 2, 3]
    assert all(entry["path"] == "f.txt" for entry in mechanical.entries)


# ---------------------------------------------------------------- worktree

def test_temporary_worktree_cleans_up_on_success(tmp_path):
    repo = _clean_merge_repo(tmp_path)
    before = gitobj.worktree_list(repo)
    with gitobj.temporary_worktree(repo, "side") as path:
        assert os.path.isdir(path)
        assert len(gitobj.worktree_list(repo)) == len(before) + 1
    assert gitobj.worktree_list(repo) == before


def test_temporary_worktree_cleans_up_on_exception(tmp_path):
    repo = _clean_merge_repo(tmp_path)
    before = gitobj.worktree_list(repo)
    with pytest.raises(RuntimeError):
        with gitobj.temporary_worktree(repo, "side"):
            raise RuntimeError("boom")
    assert gitobj.worktree_list(repo) == before
