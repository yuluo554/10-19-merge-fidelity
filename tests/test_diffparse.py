"""unified diff / remerge-diff 解析的守门测试（用实测抓到的真实输出形态）。"""

from mergefidelity import diffparse

EVIL_MERGE = (
    "cc8d1b36f421a5c2dca9c0a471ea7dd35ff14ce2\x00"
    "ebf5fbaac19c211974ebc96539984f34dfb3850c 844ceb33bfffbafbd1b04f374f507137ee2d812e\n"
    "\n"
    "diff --git a/f.txt b/f.txt\n"
    "index e80b0c1..b99a119 100644\n"
    "--- a/f.txt\n"
    "+++ b/f.txt\n"
    "@@ -1,3 +1,4 @@\n"
    " a\n"
    " b\n"
    " C-main\n"
    "+SMUGGLED\n"
)

RESOLVED_CONFLICT = (
    "a6a4889fd4e699cac122de2f216fe1e4af6d7b3d\x00"
    "0ff1e07528d201b082cd9ed6ff7aa8662fa0bdd5 8b87c1e0034d103c7917ce5b7a0aa608ad5126aa\n"
    "\n"
    "diff --git a/f.txt b/f.txt\n"
    "remerge CONFLICT (content): Merge conflict in f.txt\n"
    "index 45a4fa6..aedf1d5 100644\n"
    "--- a/f.txt\n"
    "+++ b/f.txt\n"
    "@@ -1,9 +1,5 @@\n"
    " a\n"
    "-<<<<<<< 0ff1e07 (main)\n"
    "-B-main\n"
    "-=======\n"
    "-B-side\n"
    "->>>>>>> 8b87c1e (side)\n"
    "+B-resolved\n"
    " c\n"
)

FAITHFUL = (
    "9b4de65bea3e4c272c2d14626f5661fa80f93d9e\x00"
    "ebf5fbaac19c211974ebc96539984f34dfb3850c 844ceb33bfffbafbd1b04f374f507137ee2d812e\n"
)


def test_parse_remerge_log_evil_merge():
    entries = diffparse.parse_remerge_log(EVIL_MERGE)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.commit_oid.startswith("cc8d1b36")
    assert entry.parents == (
        "ebf5fbaac19c211974ebc96539984f34dfb3850c",
        "844ceb33bfffbafbd1b04f374f507137ee2d812e",
    )
    assert len(entry.hunks) == 1
    hunk = entry.hunks[0]
    assert hunk.path == "f.txt"
    # git hunk 头为 1 基；本解析器按 data/README §4.5 归一为 0 基
    assert (hunk.old_start, hunk.old_count) == (0, 3)
    assert (hunk.new_start, hunk.new_count) == (0, 4)
    assert hunk.has_conflict_marker is False
    assert hunk.in_conflict_region is False
    assert "+SMUGGLED" in hunk.lines


def test_parse_remerge_log_conflict_resolution_is_flagged():
    entry = diffparse.parse_remerge_log(RESOLVED_CONFLICT)[0]
    assert entry.conflict_notes == ("remerge CONFLICT (content): Merge conflict in f.txt",)
    hunk = entry.hunks[0]
    # 被删掉的冲突标记行属于该 hunk 的内容 → 标记为冲突区
    assert hunk.has_conflict_marker is True
    assert hunk.in_conflict_region is True
    assert hunk.old_count == 9 and hunk.new_count == 5


def test_parse_remerge_log_faithful_merge_has_no_hunks():
    entries = diffparse.parse_remerge_log(FAITHFUL)
    assert len(entries) == 1
    assert entries[0].parents.__len__() == 2
    assert entries[0].hunks == ()


def test_zero_based_line_numbers_match_git_hunk_header():
    # git hunk 头是 1 基；本解析器按 data/README §4.3 用 0 基
    text = (
        "diff --git a/a.txt b/a.txt\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -5 +5 @@ tail\n"
        "-old\n"
        "+new\n"
    )
    hunk = diffparse.parse_unified_diff(text)[0]
    assert (hunk.old_start, hunk.old_count) == (4, 1)
    assert (hunk.new_start, hunk.new_count) == (4, 1)


def test_binary_diff_is_flagged_not_counted_as_lines():
    text = (
        "diff --git a/logo.png b/logo.png\n"
        "index 1111111..2222222 100644\n"
        "Binary files a/logo.png and b/logo.png differ\n"
    )
    hunks = diffparse.parse_unified_diff(text)
    assert len(hunks) == 1
    assert hunks[0].binary is True
    assert hunks[0].lines == ()


def test_path_with_spaces_is_parsed():
    text = (
        "diff --git a/dir with space/f.txt b/dir with space/f.txt\n"
        "--- a/dir with space/f.txt\n"
        "+++ b/dir with space/f.txt\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+b\n"
    )
    assert diffparse.parse_unified_diff(text)[0].path == "dir with space/f.txt"


def test_empty_diff_returns_empty_list():
    assert diffparse.parse_unified_diff("") == []
    assert diffparse.parse_unified_diff("\n\n") == []
