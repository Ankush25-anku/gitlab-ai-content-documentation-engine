"""Publishing adapters: Markdown file, CMS-ready JSON, and a GitLab merge request."""
import json
from pathlib import Path
from urllib.parse import quote

import httpx
import yaml

from ai.evaluation.quality import strip_internal_markers
from ai.schemas import Draft, PublishPackage, SourceRef
from ai.text_utils import citations, draft_to_markdown
from backend.config import get_settings
from backend.services.errors import AppError


def render_markdown(draft: Draft, package: PublishPackage, sources: list[SourceRef], keep_citations: bool = False) -> str:
    body = draft_to_markdown(draft)
    used = sorted(set(citations(body)), key=lambda x: int(x[1:]))
    by_id = {s.id: s for s in sources}
    if not keep_citations:
        body = strip_internal_markers(body)
    # The H1 comes from front matter in GitLab docs, so drop the duplicate title line.
    body = body.split("\n", 1)[1].lstrip() if body.startswith("# ") else body
    front = yaml.safe_dump(package.front_matter.model_dump(), sort_keys=False, allow_unicode=True).strip()
    footer = ""
    if keep_citations and used:
        footer = "\n## Sources\n\n" + "\n".join(f"- [{u}] {by_id[u].title}" for u in used if u in by_id) + "\n"
    return f"---\n{front}\n---\n\n# {draft.title}\n\n{body.rstrip()}\n{footer}"


def export_markdown(job_id: str, markdown: str, package: PublishPackage) -> str:
    out = Path(get_settings().export_dir) / job_id / package.file_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    return str(out)


def export_cms_json(draft: Draft, package: PublishPackage) -> dict:
    return {
        "slug": package.slug, "title": draft.title, "summary": strip_internal_markers(draft.summary),
        "content_type": package.front_matter.content_type, "channel": package.target_channel,
        "owner": package.owner, "approved_by": package.approved_by, "labels": package.labels,
        "blocks": [{"type": "section", "heading": s.heading, "markdown": strip_internal_markers(s.body_markdown)}
                   for s in draft.sections],
        "metadata": package.front_matter.model_dump(),
    }


def export_gitlab_mr(job_id: str, markdown: str, package: PublishPackage,
                     client: httpx.Client | None = None) -> dict:
    s = get_settings()
    if not (s.gitlab_token and s.gitlab_project_id):
        raise AppError("EXPORT_FAILED", "GitLab export is not configured (set GITLAB_TOKEN and GITLAB_PROJECT_ID).",
                       job_id)
    api = f"{s.gitlab_url.rstrip('/')}/api/v4/projects/{quote(str(s.gitlab_project_id), safe='')}"
    branch = f"docs/{package.slug}-{job_id[:8]}"
    own_client = client is None
    client = client or httpx.Client(timeout=30)
    headers = {"PRIVATE-TOKEN": s.gitlab_token}
    try:
        r = client.post(f"{api}/repository/branches", headers=headers,
                        params={"branch": branch, "ref": s.gitlab_target_branch})
        if r.status_code not in (201, 400):  # 400 = branch already exists (retry)
            r.raise_for_status()
        exists = client.get(f"{api}/repository/files/{quote(package.file_path, safe='')}", headers=headers,
                            params={"ref": branch}).status_code == 200
        r = client.post(f"{api}/repository/commits", headers=headers, json={
            "branch": branch, "commit_message": package.mr_title,
            "actions": [{"action": "update" if exists else "create", "file_path": package.file_path,
                         "content": markdown}]})
        r.raise_for_status()
        r = client.post(f"{api}/merge_requests", headers=headers, json={
            "source_branch": branch, "target_branch": s.gitlab_target_branch, "title": package.mr_title,
            "description": package.mr_description, "labels": ",".join(package.labels),
            "remove_source_branch": True})
        if r.status_code == 409:  # MR already open for this branch
            existing = client.get(f"{api}/merge_requests", headers=headers,
                                  params={"source_branch": branch, "state": "opened"}).json()
            return {"mr_url": existing[0]["web_url"], "branch": branch, "iid": existing[0]["iid"]}
        r.raise_for_status()
        mr = r.json()
        return {"mr_url": mr["web_url"], "branch": branch, "iid": mr["iid"]}
    except httpx.HTTPError as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")[:300]
        raise AppError("EXPORT_FAILED", f"GitLab API error: {exc} {detail}".strip(), job_id) from exc
    finally:
        if own_client:
            client.close()


def to_json(obj) -> str:
    return json.dumps(obj, indent=2, default=str)
