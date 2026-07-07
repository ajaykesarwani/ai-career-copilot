"""
Agent 2 — GitHub Deep Enrichment
=================================
Reads ALL public repositories (paginated, up to 100), fetches per-repo
metadata (topics, primary language, recent commit date), pinned repos via
GraphQL, the profile README, and contribution activity.

Stores structured repo objects (not flat strings) so the document generator
can do real relevance matching against a specific job's required skills.
"""

import os
import re
import asyncio
import httpx
from .base import BaseAgent
from utils.observability import traced


class GitHubAgent(BaseAgent):
    name = "GitHubAgent"
    system = (
        "You are a technical recruiter who evaluates developer GitHub profiles. "
        "Analyse which repos are most impressive and most relevant to specific roles."
    )

    @traced("GitHubAgent", "enrich")
    async def enrich(self, github_url: str) -> dict:
        username = github_url.rstrip("/").split("/")[-1].split("?")[0]
        headers  = self._headers()

        async with httpx.AsyncClient(timeout=20) as client:
            # Run all fetches concurrently
            repos_task       = self._fetch_all_repos(client, headers, username)
            pinned_task      = self._fetch_pinned(client, headers, username)
            readme_task      = self._fetch_profile_readme(client, headers, username)
            contrib_task     = self._fetch_contribution_summary(client, headers, username)

            repos, pinned, readme_text, contributions = await asyncio.gather(
                repos_task, pinned_task, readme_task, contrib_task,
                return_exceptions=True,
            )

        repos        = repos        if isinstance(repos, list)  else []
        pinned       = pinned       if isinstance(pinned, list) else []
        readme_text  = readme_text  if isinstance(readme_text, str)  else ""
        contributions = contributions if isinstance(contributions, str) else ""

        if not repos and not pinned:
            return {
                "github_repos":        [],
                "github_repos_rich":   [],
                "github_languages":    [],
                "github_pinned":       [],
                "github_readme_summary": "",
                "github_contributions":  "",
                "github_summary":        "",
            }

        # Aggregate language bytes across all repos (not just top-6)
        languages: dict[str, int] = {}
        for r in repos:
            for lang, byt in (r.get("_lang_bytes") or {}).items():
                languages[lang] = languages.get(lang, 0) + byt

        # Build structured repo list for relevance matching
        repo_objects = self._build_repo_objects(repos, pinned)

        # Gemini summary (for profile analysis and bio)
        summary = await self._generate_summary(
            username, repos, pinned, languages, readme_text, contributions
        )

        return {
            # Flat display strings (backward compat — UI sidebar, merger agent)
            "github_repos": [
                f"{r['name']} ⭐{r['stars']}"
                + (f" — {r['description']}" if r.get("description") else "")
                for r in repo_objects[:10]
            ],
            # Rich structured objects — used by doc_generator for job-relevance matching
            "github_repos_rich": repo_objects,
            "github_languages": [
                f"{k} {round(v / sum(languages.values()) * 100)}%"
                for k, v in sorted(languages.items(), key=lambda x: -x[1])[:6]
            ] if languages else [],
            "github_pinned": [
                f"{p['name']} ({p.get('primaryLanguage', '')}) ⭐{p.get('stars', 0)} — {p.get('description', '')}"
                for p in pinned
            ],
            "github_readme_summary": readme_text[:800] if readme_text else "",
            "github_contributions":  contributions,
            "github_summary":        summary.strip(),
        }

    # ── Fetch ALL public repos (paginated up to 100) ──────────────────────────

    async def _fetch_all_repos(
        self, client: httpx.AsyncClient, headers: dict, username: str
    ) -> list[dict]:
        """
        Fetch up to 100 public repos across multiple pages.
        For each repo, also fetch topics (need a separate Accept header)
        and language breakdown.
        """
        all_repos: list[dict] = []

        # Page through results — free tier limit is 100 items max sensibly
        for page in range(1, 5):  # pages 1-4 × 25 = up to 100 repos
            try:
                r = await client.get(
                    f"https://api.github.com/users/{username}/repos",
                    headers=headers,
                    params={
                        "sort": "updated",   # most recently touched first
                        "direction": "desc",
                        "per_page": 25,
                        "page": page,
                        "type": "owner",
                    },
                )
                if r.status_code != 200:
                    break
                page_repos = r.json()
                if not page_repos:
                    break
                all_repos.extend(page_repos)
                if len(page_repos) < 25:
                    break  # last page
            except Exception:
                break

        # For each repo, fetch languages concurrently (cap at 30 to stay within rate limits)
        await asyncio.gather(
            *[self._attach_languages(client, headers, repo) for repo in all_repos[:30]],
            return_exceptions=True,
        )

        # Fetch topics for repos that don't have them in the REST response
        # (topics are included in repo objects from 2017+ API versions — they should be present)
        return all_repos

    async def _attach_languages(
        self, client: httpx.AsyncClient, headers: dict, repo: dict
    ):
        """Fetch language breakdown for one repo and attach it as _lang_bytes."""
        try:
            r = await client.get(repo["languages_url"], headers=headers)
            if r.status_code == 200:
                repo["_lang_bytes"] = r.json()
        except Exception:
            repo["_lang_bytes"] = {}

    def _build_repo_objects(self, repos: list[dict], pinned: list[dict]) -> list[dict]:
        """
        Build structured, job-matchable repo objects from raw API responses.
        Each object has: name, description, stars, topics, languages,
        primary_language, last_updated, url, is_pinned, fork.
        """
        pinned_names = {p["name"] for p in pinned}
        objects: list[dict] = []

        for r in repos:
            if r.get("fork") and r.get("stargazers_count", 0) < 5:
                continue  # skip low-star forks — usually not the candidate's work

            lang_bytes = r.get("_lang_bytes", {})
            primary_lang = (
                max(lang_bytes, key=lang_bytes.get)
                if lang_bytes else (r.get("language") or "")
            )
            # topics come directly from the REST API response
            topics = r.get("topics", [])

            objects.append({
                "name":             r.get("name", ""),
                "description":      (r.get("description") or "").strip(),
                "stars":            r.get("stargazers_count", 0),
                "forks":            r.get("forks_count", 0),
                "topics":           topics,
                "languages":        list((r.get("_lang_bytes") or {}).keys()),
                "primary_language": primary_lang,
                "last_updated":     (r.get("pushed_at") or r.get("updated_at") or "")[:10],
                "url":              r.get("html_url", ""),
                "is_pinned":        r["name"] in pinned_names,
                "fork":             bool(r.get("fork")),
            })

        # Sort: pinned first, then by stars, then by recency (string sort on YYYYMMDD)
        objects.sort(
            key=lambda o: (
                not o["is_pinned"],  # pinned repos first
                -int(o.get("stars", 0) or 0),  # higher stars first
                (o.get("last_updated") or "0000-00-00").replace("-", ""),  # newer dates later
            )
        )
        return objects

    async def _generate_summary(
        self,
        username: str,
        repos: list[dict],
        pinned: list[dict],
        languages: dict,
        readme_text: str,
        contributions: str,
    ) -> str:
        """Generate a 3-sentence professional summary of the GitHub profile."""
        repo_lines = "\n".join(
            f"- {r.get('name')} ⭐{r.get('stargazers_count', 0)}"
            f"{': ' + r['description'] if r.get('description') else ''}"
            f" [{r.get('language') or ''}]"
            f" topics: {','.join(r.get('topics', [])[:4])}"
            for r in repos[:15]
        )
        pinned_lines = "\n".join(
            f"- {p['name']} ({p.get('primaryLanguage','')}) ⭐{p.get('stars',0)}: {p.get('description','')}"
            for p in pinned
        ) if pinned else ""
        lang_str = ", ".join(
            f"{k} {round(v/sum(languages.values())*100)}%"
            for k, v in sorted(languages.items(), key=lambda x: -x[1])[:6]
        ) if languages else ""

        try:
            return await self.call([{
                "role": "user",
                "content": (
                    f"GitHub: {username}\n"
                    f"Repos (sorted by recency, {len(repos)} total):\n{repo_lines}\n"
                    + (f"Pinned:\n{pinned_lines}\n" if pinned_lines else "")
                    + (f"Languages: {lang_str}\n" if lang_str else "")
                    + (f"Profile README excerpt:\n{readme_text[:500]}\n" if readme_text else "")
                    + (f"Contributions: {contributions}\n" if contributions else "")
                    + "\nWrite 3 specific sentences summarising this developer's technical "
                      "strengths, most impressive open-source work, and contribution style. "
                      "Reference actual project names and technologies. Be specific."
                )
            }], max_tokens=250)
        except Exception:
            return ""

    # ── GraphQL: pinned repos ─────────────────────────────────────────────────

    async def _fetch_pinned(
        self, client: httpx.AsyncClient, headers: dict, username: str
    ) -> list:
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return []

        query = """
        query($login: String!) {
          user(login: $login) {
            pinnedItems(first: 6, types: REPOSITORY) {
              nodes {
                ... on Repository {
                  name
                  description
                  stargazerCount
                  primaryLanguage { name }
                  repositoryTopics(first: 5) { nodes { topic { name } } }
                  url
                  pushedAt
                }
              }
            }
          }
        }
        """
        try:
            resp = await client.post(
                "https://api.github.com/graphql",
                headers={**headers, "Authorization": f"Bearer {token}"},
                json={"query": query, "variables": {"login": username}},
            )
            if resp.status_code == 200:
                data  = resp.json()
                nodes = (
                    (data.get("data") or {})
                    .get("user", {})
                    .get("pinnedItems", {})
                    .get("nodes", [])
                ) or []
                return [
                    {
                        "name":            n["name"],
                        "description":     n.get("description", ""),
                        "stars":           n.get("stargazerCount", 0),
                        "primaryLanguage": (n.get("primaryLanguage") or {}).get("name", ""),
                        "topics": [
                            tn["topic"]["name"]
                            for tn in (n.get("repositoryTopics") or {}).get("nodes", [])
                        ],
                        "url":             n.get("url", ""),
                        "last_updated":    (n.get("pushedAt") or "")[:10],
                    }
                    for n in nodes if n
                ]
        except Exception:
            pass
        return []

    # ── REST: profile README ──────────────────────────────────────────────────

    async def _fetch_profile_readme(
        self, client: httpx.AsyncClient, headers: dict, username: str
    ) -> str:
        for branch in ("main", "master"):
            try:
                url = (f"https://raw.githubusercontent.com/"
                       f"{username}/{username}/{branch}/README.md")
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    text = r.text
                    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
                    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
                    text = re.sub(r"```[\s\S]*?```", "", text)
                    text = re.sub(r"<[^>]+>", "", text)
                    text = re.sub(r"\n{3,}", "\n\n", text).strip()
                    return text[:1500]
            except Exception:
                continue
        return ""

    # ── REST: contribution activity ───────────────────────────────────────────

    async def _fetch_contribution_summary(
        self, client: httpx.AsyncClient, headers: dict, username: str
    ) -> str:
        try:
            r = await client.get(
                f"https://api.github.com/users/{username}/events/public",
                headers=headers,
                params={"per_page": 30},
            )
            if r.status_code != 200:
                return ""
            events = r.json()
            type_counts: dict[str, int] = {}
            repos_touched: set[str] = set()
            for ev in events:
                t = ev.get("type", "")
                type_counts[t] = type_counts.get(t, 0) + 1
                rn = (ev.get("repo") or {}).get("name", "")
                if rn:
                    repos_touched.add(rn)
            parts = []
            if type_counts.get("PushEvent"):
                parts.append(f"{type_counts['PushEvent']} commits")
            if type_counts.get("PullRequestEvent"):
                parts.append(f"{type_counts['PullRequestEvent']} PRs")
            if type_counts.get("IssuesEvent"):
                parts.append(f"{type_counts['IssuesEvent']} issues")
            if repos_touched:
                parts.append(f"across {len(repos_touched)} repos recently")
            return ", ".join(parts) if parts else ""
        except Exception:
            return ""

    def _headers(self) -> dict:
        h = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = os.getenv("GITHUB_TOKEN")
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h
