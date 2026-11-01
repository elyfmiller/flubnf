"""The contributor check: a fork's pull request, read as data.

.github/workflows/contributor-check.yml runs this file on
pull_request_target, as it is on the default branch, with a read-only token.
It reads the pull request through GitHub's REST API (its commits, its files
and, when a changed path is under proposals/, the head tree and the base
branch's proposal folders) and runs none of it. docs/CONTRIBUTING.md
section 7 says the same rules to a contributor.

Refused (an ::error:: line each, exit 1):
- a base branch other than dev;
- more commits or files than the check reads, or a tree too large to read;
- a co-author or generated-by line in a commit message, the title or the
  description;
- a commit under the repository owner's account or address that is not
  already on the default branch;
- a proposals/<name>/ folder that is not six plain files of at most 256 KB.

Flagged (a ::warning:: line each; the check stays green on flags alone):
- a change to the launchers, the installers, .github/ or the engine updater;
- a commit linked to another GitHub account than the opener's.

No line of the pull request's own text is printed: only the rules' words,
short shas, line numbers and escaped paths, so nothing in it can start a
workflow command. Standard library only, Python 3.10 or later.

Usage (the workflow's run line; it reads GITHUB_EVENT_PATH,
GITHUB_REPOSITORY, GITHUB_API_URL and GITHUB_TOKEN):
    python3 -I .github/contributor_check.py

Exit status 0 when nothing is refused, 1 on a refusal or when the check
could not finish.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Callable

OWNER_EMAILS = ("efm46@nau.edu",)          # the only address written; noreply forms are derived
WEB_COMMITTER = "web-flow"                 # GitHub's own committer of website edits and merges
FORK_BASE = "dev"
PROPOSAL_FILES = ("README.md", "experiment.json", "model.bngl", "model.json",
                  "priors.conf", "summary.json")
PROPOSAL_MAX = 256 * 1024
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")      # sandbox.NAME_RE
SHIPPED_NAMES = ("sihrs", "sihrs-2strain", "sihrs-natg")      # library.SHIPPED_NAMES
MAX_COMMITS, MAX_FILES = 250, 3000
FLAGGED = (   # (group, what it is, paths); a trailing / is a folder; matched ignoring case
    ("the launchers", "run on every computer that installs FluBNF",
     ("FluBNF.command", "FluBNF.app/", "FluBNF.bat", "SetupEngine.command",
      "scripts/macos/", "scripts/windows/")),
    ("the installers", "run on every computer that installs FluBNF",
     ("install.sh", "reinstall.sh", "setup.sh", "setup_engine.sh", "setup.ps1",
      "pyproject.toml", ".githooks/", ".gitattributes")),
    ("CI and this check", "run on GitHub for every pull request", (".github/",)),
    ("the engine updater", "run on every computer that installs FluBNF",
     ("app/core/engine_update.py", "app/core/engine_build.py", "flubnf/cli_doctor.py",
      "scripts/cut_engine_archive.sh", "scripts/engine_lock.py", "engine-requirements.txt")),
)
_TAG = re.compile(r"<[^>]*>")
_LEAD = re.compile(r"^(?:\[[ xX]\]|[^A-Za-z])+")       # a checkbox's x too
_CREDIT = re.compile(r"(co[-\s]?(authored|written|developed)|generated|assisted)"
                     r"[-\s]+(by|with|using)\b", re.I)
_SHA = re.compile(r"[0-9a-f]{40}")
_MODES = {"120000": "a symbolic link", "100755": "an executable", "160000": "a submodule"}


def credit_lines(text: str) -> list[int]:
    """The numbers (from 1) of the lines that credit a co-author or say the
    text was generated. Each line loses its <...> tags, then everything
    before its first letter (a checkbox's [x] with it), and is matched at
    its start, so quoting, bold, list marks, a checkbox and an emoji in
    front change nothing."""
    return [i for i, line in enumerate(text.splitlines(), 1)
            if _CREDIT.match(_LEAD.sub("", _TAG.sub("", line)))]


def owner_addresses(login: str, uid: int) -> set[str]:
    """The repository owner's addresses, lowercased: OWNER_EMAILS and the
    account's two noreply forms, derived from its login and id."""
    noreply = "users.noreply.github.com"
    return {a.lower() for a in (*OWNER_EMAILS, f"{uid}+{login}@{noreply}",
                                f"{login}@{noreply}")}


def commit_problems(commits: list[dict], *, owner: str, uid: int, opener: str,
                    in_main: Callable[[str], bool]) -> tuple[list[str], list[str]]:
    """(refusals, flags) for the pull request's commits. A credit line is
    refused in every commit. The owner's account or address is refused,
    and another account than the opener's flagged, only in a commit not
    already on the default branch; in_main(sha) is asked only then."""
    refusals: list[str] = []
    flags: list[str] = []
    addresses = owner_addresses(owner, uid)
    owner, opener = owner.lower(), opener.lower()
    for c in commits:
        sha = c["sha"]
        if not _SHA.fullmatch(sha):
            raise ValueError("a commit sha that is not 40 hex characters")
        meta = c.get("commit") or {}
        lines = credit_lines(meta.get("message") or "")
        if lines:
            refusals.append(f"commit `{sha[:8]}` has a co-author or generated-by line "
                            f"({_lines(lines)}): everything here is written by people, "
                            "under their own name. Remove or reword the line and push again.")
        as_owner, other = [], []
        for role, side, allowed in (("authored", "author", {owner, opener}),
                                    ("committed", "committer", {owner, opener, WEB_COMMITTER})):
            login = ((c.get(side) or {}).get("login") or "").lower()
            email = ((meta.get(side) or {}).get("email") or "").lower()
            if login == owner or email in addresses:
                as_owner.append(role)
            elif login and login not in allowed:
                other.append(role)
        if not (as_owner or other) or in_main(sha):
            continue
        if as_owner:
            refusals.append(f"commit `{sha[:8]}` is {_and(as_owner)} under the repository "
                            "owner's account or address: a contributor's pull request carries "
                            "the contributor's own commits. Commit under your own name and "
                            "address (git config user.name and user.email in your clone), "
                            "then push again.")
        if other:
            flags.append(f"commit `{sha[:8]}` is {_and(other)} under another GitHub account "
                         "than this pull request's.")
    return refusals, flags


def path_flags(files: list[dict]) -> list[str]:
    """A flag for each changed path, or a rename's old path, that FLAGGED
    names, matched ignoring case as macOS and Windows folders ignore it
    (casefold: the long s reads as s there). A .gitattributes in any
    folder counts as the top one: each sets the checked-out bytes below it."""
    out: list[str] = []
    for name in dict.fromkeys(_names(files)):
        low = name.casefold()
        if low.rsplit("/", 1)[-1] == ".gitattributes":
            low = ".gitattributes"
        for group, what, paths in FLAGGED:
            if any(low.startswith(p.casefold()) if p.endswith("/") else low == p.casefold()
                   for p in paths):
                out.append(f"`{_escape(name)}` is part of {group}, which {what}: "
                           "read the change line by line before approving its tests.")
                break
    return out


def proposal_problems(files: list[dict], tree: dict | None,
                      base: list[str] = ()) -> list[str]:
    """Refusals for each proposals/<name>/ folder a changed path touches,
    read from the head tree's entries (git/trees/<head>?recursive=1; None
    when no changed path is under proposals/). A folder the head tree no
    longer holds was removed, and passes. Folder names that differ only in
    letter case are refused across all of proposals/, with the base
    branch's proposal folders (`base`, their names) among them."""
    if tree is None:
        return []
    entries = {e["path"]: e for e in tree.get("tree") or []}
    out: list[str] = []
    touched: set[str] = set()
    for name in _names(files):
        top, _, rest = name.partition("/")
        if top.casefold() != "proposals":
            continue
        if not rest:
            # a file, link or submodule where the proposals folder goes
            if (entries.get(name) or {}).get("type") not in (None, "tree"):
                out.append(f"`{_escape(name)}` is outside a proposal folder.")
        elif top != "proposals":
            if name in entries:
                out.append(f"`{_escape(name)}` is under a proposals folder written in "
                           "other letter case: use proposals/ in lowercase.")
        elif "/" not in rest:
            if name in entries:
                out.append(f"`{_escape(name)}` is outside a proposal folder.")
        else:
            touched.add(rest.split("/")[0])
    twins: dict[str, list[str]] = {}
    for path, e in entries.items():
        top, _, rest = path.partition("/")
        if top == "proposals" and rest and "/" not in rest:
            twins.setdefault(rest.casefold(), []).append(
                path + ("/" if e.get("type") == "tree" else ""))
    # a branch cut before another proposal merged lacks it in its own tree
    for name in base:
        if f"proposals/{name}" not in entries:
            twins.setdefault(name.casefold(), []).append(f"proposals/{name}/")
    for group in sorted(twins.values()):
        if len(group) > 1:
            out.append(f"{_and([f'`{_escape(p)}`' for p in sorted(group)])} differ only "
                       "in letter case: macOS and Windows folders ignore case; keep one.")
    for name in sorted(touched):
        folder = f"proposals/{name}"
        if (entries.get(folder) or {}).get("type") != "tree":
            continue
        if not NAME_RE.fullmatch(name) or name.lower() in SHIPPED_NAMES:
            out.append(f"`{_escape(folder)}` is not a proposal folder: a model's name "
                       "(letters, digits, _ and -, up to 64, starting with a letter or "
                       "digit) that is not a shipped model's.")
            continue
        held: set[str] = set()
        for path, e in sorted(entries.items()):
            if not path.startswith(folder + "/") or "/" in path[len(folder) + 1:]:
                continue    # outside this folder, or below one of its folders
            rest = path[len(folder) + 1:]
            shown = _escape(path)
            if e.get("type") == "tree":
                out.append(f"`{shown}/` is a folder inside a proposal: a proposal holds "
                           "its six files only.")
            elif rest not in PROPOSAL_FILES:
                out.append(f"`{shown}` is not a proposal file: a proposal holds "
                           f"{_and(list(PROPOSAL_FILES))} only.")
            else:
                held.add(rest)
                if e.get("mode") in _MODES:
                    out.append(f"`{shown}` is {_MODES[e['mode']]}: proposal files are "
                               "plain files.")
                elif (e.get("size") or 0) > PROPOSAL_MAX:     # KB rounded up
                    out.append(f"`{shown}` is {-(-e['size'] // 1024)} KB: a proposal file "
                               f"is at most {PROPOSAL_MAX // 1024} KB.")
        missing = [f for f in PROPOSAL_FILES if f not in held]
        if missing:
            out.append(f"`{_escape(folder)}/` lacks {_and(missing)}.")
    return out


def check(event: dict, commits, files, tree, in_main,
          base=()) -> tuple[list[str], list[str]]:
    """(refusals, flags) for a fork's pull request from what main() read:
    the event, its commits and changed files, the head tree (None when no
    changed path is under proposals/), in_main(sha), whether a commit
    is already on the default branch, and the base branch's proposal
    folders (read with the tree). It reads nothing itself."""
    pr, owner = event["pull_request"], event["repository"]["owner"]
    refusals: list[str] = []
    if pr["base"]["ref"] != FORK_BASE:
        refusals.append(f"this pull request is against `{_escape(pr['base']['ref'])}`; a pull "
                        f"request from a fork goes to {FORK_BASE}: change its base branch "
                        f"to {FORK_BASE}.")
    for count, most, what in ((int(pr["commits"]), MAX_COMMITS, "commits"),
                              (int(pr["changed_files"]), MAX_FILES, "changed files")):
        if count > most:
            refusals.append(f"this pull request has {count} {what}; the check reads at most "
                            f"{most}: open a smaller one.")
    truncated = bool(tree and tree.get("truncated"))
    if truncated:
        refusals.append("its tree is too large for the check to read: open a smaller one.")
    if credit_lines(pr.get("title") or ""):
        refusals.append("the title has a co-author or generated-by line: remove or reword it.")
    lines = credit_lines(pr.get("body") or "")
    if lines:
        refusals.append(f"the description has a co-author or generated-by line "
                        f"({_lines(lines)}): remove or reword it.")
    by_commit, flags = commit_problems(commits, owner=owner["login"], uid=owner["id"],
                                       opener=pr["user"]["login"], in_main=in_main)
    refusals += by_commit
    if not truncated:
        refusals += proposal_problems(files, tree, base)
    return refusals, flags + path_flags(files)


def _names(files: list[dict]) -> list[str]:
    """Every changed path, and the old path of each rename."""
    return [n for f in files for n in (f.get("filename"), f.get("previous_filename")) if n]


def _and(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _lines(numbers: list[int]) -> str:
    """'line 7', or 'lines 3 and 7'."""
    return ("line " if len(numbers) == 1 else "lines ") + _and([str(i) for i in numbers])


def _escape(text: str) -> str:
    """Untrusted text made safe inside one workflow-command line: JSON's
    string escapes (no raw line break or control character survives; the
    quotes JSON adds are dropped), then the runner's own escapes of %, CR
    and LF."""
    return json.dumps(text)[1:-1].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _get(path: str):
    """GET $GITHUB_API_URL/repos/$GITHUB_REPOSITORY/<path> with the job's
    token, as parsed JSON. Without those variables it raises KeyError
    before it opens any connection."""
    env = os.environ
    req = urllib.request.Request(
        f"{env['GITHUB_API_URL']}/repos/{env['GITHUB_REPOSITORY']}/{path}",
        headers={"Authorization": f"Bearer {env['GITHUB_TOKEN']}",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "flubnf-contributor-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main(environ=os.environ, get=None) -> int:
    """Read $GITHUB_EVENT_PATH's pull request through `get` (default _get),
    print the check's lines and return the exit status."""
    get = get or _get
    try:
        with open(environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            event = json.load(f)
        pr = event["pull_request"]
        # a fork: head.repo is null (a deleted fork) or another repository
        head_repo = (pr["head"].get("repo") or {}).get("full_name") or ""
        if head_repo.lower() == environ["GITHUB_REPOSITORY"].lower():
            print("contributor check: not a fork's pull request: nothing to check")
            return 0
        n, sha = int(pr["number"]), pr["head"]["sha"]
        if not _SHA.fullmatch(sha):
            raise ValueError("the head sha is not 40 hex characters")
        print(f"contributor check: pull request #{n} at {sha}")

        def pages(path: str, most: int) -> list:
            out: list = []
            for k in range(1, most + 1):
                page = get(f"{path}?per_page=100&page={k}")
                out += page
                if len(page) < 100:
                    break
            return out

        default = event["repository"]["default_branch"]

        def in_main(c: str) -> bool:
            # behind or identical: the commit is already on the default branch;
            # a 404 counts as not on it, so the check fails closed
            if not _SHA.fullmatch(c):
                raise ValueError("a commit sha that is not 40 hex characters")
            try:
                return get(f"compare/{default}...{c}")["status"] in ("behind", "identical")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return False
                raise

        commits = pages(f"pulls/{n}/commits", 3)
        files = pages(f"pulls/{n}/files", 30)
        # the lists must be the whole pull request at the event's head: an
        # answer short of the event's counts, or one without its head sha
        # (a push since), would pass what it left out, so it fails closed
        k = int(pr["commits"])
        if (len(commits) != min(k, MAX_COMMITS)
                or len(files) != min(int(pr["changed_files"]), MAX_FILES)
                or (k <= MAX_COMMITS and sha not in {c.get("sha") for c in commits})):
            raise ValueError("the commits or files read are not the pull request's")
        tree, base = None, []
        if any(name.split("/")[0].casefold() == "proposals" for name in _names(files)):
            tree = get(f"git/trees/{sha}?recursive=1")
            try:
                listed = get(f"contents/proposals?ref={FORK_BASE}")
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                listed = []                      # no proposals/ on the base yet
            if isinstance(listed, list):
                base = [x["name"] for x in listed if x.get("type") == "dir"]
        refusals, flags = check(event, commits, files, tree, in_main, base)
    except urllib.error.HTTPError as e:
        print(f"contributor check: could not read the pull request from GitHub "
              f"(HTTP {e.code}): run the check again.")
        return 1
    except Exception as e:
        print(f"contributor check: the check itself failed ({type(e).__name__}): "
              "run it again.")
        return 1
    for line in refusals:
        print(f"::error::{line}")
    for line in flags:
        print(f"::warning::{line}")
    print(f"contributor check: {len(refusals)} refused, {len(flags)} flagged")
    return 1 if refusals else 0


if __name__ == "__main__":
    sys.exit(main())
