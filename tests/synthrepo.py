"""测试用合成 git 仓库构造器（**不是**被测对象的一部分）。

供 `test_gitobj.py` / `test_cli.py` 等使用：所有可变输入固定，仓库可复现。
"""

import os
import subprocess

AUTHOR_NAME = "Fixture Bot"
AUTHOR_EMAIL = "fixture@example.invalid"
BASE_DATE = "2026-01-01T00:00:00+0000"

_counter = [0]


def _env(offset=0):
    env = dict(os.environ)
    stamp = "2026-01-01T00:00:%02d+0000" % offset
    env.update(
        {
            "GIT_AUTHOR_NAME": AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL,
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": env.get("HOME", ""),
        }
    )
    return env


def git(repo, *args, check=True):
    proc = subprocess.run(
        ["git", "-C", repo] + [str(a) for a in args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            "git %s failed (%d): %s" % (" ".join(map(str, args)), proc.returncode,
                                        proc.stderr.decode("utf-8", "replace"))
        )
    return proc


def write(repo, relpath, lines):
    path = os.path.join(repo, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def init_repo(path):
    os.makedirs(path, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", AUTHOR_NAME)
    git(path, "config", "user.email", AUTHOR_EMAIL)
    git(path, "config", "commit.gpgsign", "false")
    _counter[0] = 0
    return path


def commit(repo, message, files):
    for relpath, lines in files.items():
        write(repo, relpath, lines)
    git(repo, "add", "-A")
    _counter[0] += 1
    env = _env(_counter[0])
    subprocess.run(
        ["git", "-C", repo, "commit", "-q", "-m", message],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=True,
    )
    return git(repo, "rev-parse", "HEAD").stdout.decode().strip()
