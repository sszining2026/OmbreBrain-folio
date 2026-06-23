"""
github_sync.py — GitHub 仓库同步（用于 bucket 数据云端备份）

策略：
- 只同步 buckets_dir 下的 .md 文件（纯文本，体积小，可读性好）
- embeddings.db 不上传（二进制，可由 /api/embedding/migrate 重算）
- 使用 GitHub Git Trees API 批量提交（一次同步 = 一个 commit）
- 支持手动触发 + 可选的定时自动同步

依赖：httpx（已在 requirements.txt）
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("ombre_brain.github_sync")

_API = "https://api.github.com"
_TIMEOUT = 60.0
_MAX_FILE_BYTES = 5 * 1024 * 1024  # GitHub single blob 上限 ~100MB，这里保守限 5MB
_TREE_CHUNK = 200                  # 每个 /git/trees 请求最多内联多少文件，避免单请求过大


class GitHubSync:
    """向 GitHub 仓库批量上传 bucket .md 文件。"""

    def __init__(
        self,
        token: str,
        repo: str,
        branch: str = "main",
        path_prefix: str = "ombre",
    ):
        self.token = token
        self.repo = repo.strip()          # "owner/repo"
        self.branch = branch.strip() or "main"
        self.path_prefix = path_prefix.strip().strip("/")

        self._headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        self.last_sync: str | None = None
        self.last_status: str = "idle"   # idle | ok | error
        self.last_error: str = ""
        self.last_count: int = 0
        self.is_validated: bool = False   # validate() 成功后置 True

    # --------------------------------------------------------
    # 公开接口
    # --------------------------------------------------------

    async def sync(self, buckets_dir: str) -> dict[str, Any]:
        """同步 buckets_dir 下所有 .md 到 GitHub。返回结果 dict。"""
        try:
            files = self._collect_files(buckets_dir)
            if not files:
                self.last_status = "ok"
                self.last_error = ""
                self.last_sync = _now_iso()
                self.last_count = 0
                return {"ok": True, "uploaded": 0, "message": "无可同步文件"}

            count = await self._batch_commit(files)
            self.last_sync = _now_iso()
            self.last_status = "ok"
            self.last_error = ""
            self.last_count = count
            return {"ok": True, "uploaded": count}
        except Exception as e:
            self.last_status = "error"
            self.last_error = str(e)
            logger.error(f"[github_sync] sync failed: {e}")
            return {"ok": False, "error": str(e)}

    async def validate(self) -> dict[str, Any]:
        """验证 token + repo 可访问，且具有写权限（contents: write）。"""
        try:
            async with httpx.AsyncClient(headers=self._headers, timeout=15.0) as c:
                r = await c.get(f"{_API}/repos/{self.repo}")
                if r.status_code == 404:
                    return {"ok": False, "error": f"仓库 {self.repo} 不存在或无权限访问"}
                if r.status_code == 401:
                    return {"ok": False, "error": "Token 无效或已过期"}
                r.raise_for_status()
                data = r.json()

                # Check write permission via `permissions.push` field
                # (GitHub returns this field when authenticated)
                perms = data.get("permissions", {})
                can_push = perms.get("push", False) or perms.get("admin", False)
                if perms and not can_push:
                    return {
                        "ok": False,
                        "error": "Token 只有读权限，无法上传文件。请在 GitHub → Settings → Developer settings → Fine-grained tokens 中将 Contents 权限设为 Read and write",
                    }

                self.is_validated = True
                return {
                    "ok": True,
                    "repo_full_name": data.get("full_name", self.repo),
                    "private": data.get("private", False),
                    "default_branch": data.get("default_branch", "main"),
                    "can_push": can_push,
                }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.token and self.repo),
            "repo": self.repo,
            "branch": self.branch,
            "path_prefix": self.path_prefix,
            "last_sync": self.last_sync,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_count": self.last_count,
            "is_validated": self.is_validated,
        }

    # --------------------------------------------------------
    # 内部实现
    # --------------------------------------------------------

    def _collect_files(self, buckets_dir: str) -> dict[str, bytes]:
        """遍历 buckets_dir，收集所有 .md 文件。"""
        result: dict[str, bytes] = {}
        if not os.path.isdir(buckets_dir):
            return result
        for root, _, filenames in os.walk(buckets_dir):
            for fn in filenames:
                if not fn.endswith(".md"):
                    continue
                full = os.path.join(root, fn)
                try:
                    size = os.path.getsize(full)
                    if size > _MAX_FILE_BYTES:
                        logger.warning(f"[github_sync] skip {fn}: too large ({size} bytes)")
                        continue
                    with open(full, "rb") as f:
                        result[os.path.relpath(full, buckets_dir).replace("\\", "/")] = f.read()
                except OSError as e:
                    logger.warning(f"[github_sync] skip {fn}: {e}")
        return result

    async def _batch_commit(self, files: dict[str, bytes]) -> int:
        """用 Git Trees API 一次性提交所有文件，返回上传文件数。

        关键点：tree entry 直接内联 `content`（UTF-8 文本），由 GitHub 在建
        tree 时顺带创建 blob —— 几百个文件只需 1~N 个 /git/trees 请求，而不是
        每个文件一个 /git/blobs 请求。后者会瞬间打满 GitHub 的 *secondary rate
        limit*（返回 403），正是之前同步莫名 403 的根因。

        大批量时分块提交（每块 _TREE_CHUNK 个），块与块之间用 base_tree 串联，
        最后只打一个 commit。所有请求都带指数退避重试以应对偶发的二级限流。
        """
        async with httpx.AsyncClient(headers=self._headers, timeout=_TIMEOUT) as c:
            # 1. 获取 branch HEAD commit SHA
            r = await self._request(c, "GET", f"{_API}/repos/{self.repo}/git/ref/heads/{self.branch}")
            if r.status_code == 404:
                raise RuntimeError(f"分支 {self.branch} 不存在，请先在 GitHub 上创建该分支")
            r.raise_for_status()
            head_sha: str = r.json()["object"]["sha"]

            # 2. 获取 HEAD commit 对应的 tree SHA
            r = await self._request(c, "GET", f"{_API}/repos/{self.repo}/git/commits/{head_sha}")
            r.raise_for_status()
            base_tree_sha: str = r.json()["tree"]["sha"]

            # 3. 组装 tree entries（内联 content，文本直接走 UTF-8）
            entries: list[dict] = []
            for rel_path, content in files.items():
                gh_path = f"{self.path_prefix}/{rel_path}" if self.path_prefix else rel_path
                try:
                    text = content.decode("utf-8")
                    entry = {"path": gh_path, "mode": "100644", "type": "blob", "content": text}
                except UnicodeDecodeError:
                    # 非 UTF-8（理论上只同步 .md，不会走到这里）：退回 base64 blob
                    rb = await self._request(
                        c, "POST", f"{_API}/repos/{self.repo}/git/blobs",
                        json={"content": base64.b64encode(content).decode(), "encoding": "base64"},
                    )
                    rb.raise_for_status()
                    entry = {"path": gh_path, "mode": "100644", "type": "blob", "sha": rb.json()["sha"]}
                entries.append(entry)

            # 4. 分块创建 tree，块间用 base_tree 串联
            cur_base = base_tree_sha
            for i in range(0, len(entries), _TREE_CHUNK):
                chunk = entries[i:i + _TREE_CHUNK]
                r = await self._request(
                    c, "POST", f"{_API}/repos/{self.repo}/git/trees",
                    json={"base_tree": cur_base, "tree": chunk},
                )
                r.raise_for_status()
                cur_base = r.json()["sha"]
            new_tree_sha = cur_base

            # 5. 创建 commit
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            r = await self._request(
                c, "POST", f"{_API}/repos/{self.repo}/git/commits",
                json={
                    "message": f"Ombre Brain sync — {now_str} ({len(files)} files)",
                    "tree": new_tree_sha,
                    "parents": [head_sha],
                },
            )
            r.raise_for_status()
            commit_sha: str = r.json()["sha"]

            # 6. 更新 branch ref
            r = await self._request(
                c, "PATCH", f"{_API}/repos/{self.repo}/git/refs/heads/{self.branch}",
                json={"sha": commit_sha, "force": False},
            )
            r.raise_for_status()

        return len(files)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        _max_retries: int = 4,
    ) -> httpx.Response:
        """带退避重试的请求。专治 GitHub 二级限流（403/429 + Retry-After）。

        普通 4xx（权限/404 等）直接返回交由上层 raise_for_status 处理，不重试。
        """
        for attempt in range(_max_retries + 1):
            resp = await client.request(method, url, json=json)
            if resp.status_code not in (403, 429):
                return resp
            # 判断是否二级限流（而非真正的权限 403）
            body_l = resp.text.lower()
            is_rate = (
                "rate limit" in body_l
                or "retry-after" in {k.lower() for k in resp.headers}
                or resp.headers.get("x-ratelimit-remaining") == "0"
            )
            if not is_rate or attempt == _max_retries:
                return resp
            # 计算等待时长：优先 Retry-After，其次指数退避
            retry_after = resp.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                wait = int(retry_after)
            else:
                wait = min(2 ** attempt, 30)
            logger.warning(f"[github_sync] secondary rate limit, retry in {wait}s (attempt {attempt + 1})")
            await asyncio.sleep(wait)
        return resp


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
