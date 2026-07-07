"""
Agent 3 — Profile Merger & Ranker
Merges resume + GitHub + LinkedIn into unified candidate profile,
then scores profile strength and generates analysis.
"""

import re
from .base import BaseAgent
from utils.observability import traced


class ProfileMergerAgent(BaseAgent):
    name = "ProfileMerger"
    system = (
        "You are a senior talent strategist. You synthesise candidate data from multiple sources "
        "into clear, actionable career insights. Be specific, honest, and practical."
    )

    @traced("ProfileMerger", "merge_and_analyse")
    async def merge_and_analyse(self, profile_data: dict, preferences: dict) -> dict:
        """Return merged profile with strength score and analysis."""

        context = f"""CANDIDATE DATA:
Name: {profile_data.get('name','')}
Title: {profile_data.get('title','')}
Skills: {', '.join(profile_data.get('skills', []))}
Years experience: {profile_data.get('years_exp', 0)}
Summary: {profile_data.get('summary','')}
GitHub repos: {', '.join(profile_data.get('github_repos', [])[:5])}
GitHub languages: {', '.join(profile_data.get('github_languages', []))}
GitHub summary: {profile_data.get('github_summary','')}
LinkedIn/bio: {profile_data.get('linkedin_text','')[:500] or profile_data.get('bio','')}
Top projects: {', '.join(profile_data.get('top_projects', [])[:3])}

JOB PREFERENCES:
Target roles: {preferences.get('roles','')}
Locations: {preferences.get('locations','')}
Salary: {preferences.get('salary','')}
Seniority: {preferences.get('seniority','')}
Industries: {preferences.get('industries','')}
Work mode: {'Remote' if preferences.get('remote') else ''} {'Hybrid' if preferences.get('hybrid') else ''} {'On-site' if preferences.get('onsite') else ''}"""

        analysis = await self.call([{"role": "user", "content": f"""{context}

Provide a comprehensive career analysis with these exact sections:

1. PROFILE STRENGTH: [N]/100 — [one sentence reason]

2. SKILL GAPS (top 3 to address):
• [skill] — [why it matters for target roles]
• [skill] — [why it matters]
• [skill] — [why it matters]

3. BEST-FIT ROLES (3-4 roles):
• [Role title] — [why it fits]

4. UNIQUE VALUE PROPOSITION:
[2-3 sentences on what makes this candidate distinctive in the market]

5. RECOMMENDED SEARCH KEYWORDS:
[8-10 keywords/phrases for job search]

6. QUICK WIN:
[One specific, actionable tip to improve profile or job search right now]

Be concrete. Use numbers and specifics. Avoid generic career advice."""}],
            max_tokens=1200
        )

        # Extract strength score
        score_match = re.search(r"(\d{2,3})\s*/\s*100", analysis)
        strength_score = int(score_match.group(1)) if score_match else 72

        # Extract suggested skills from gap section
        gap_matches = re.findall(r"•\s+([A-Za-z][A-Za-z0-9\+\#\. ]{1,30})\s+—", analysis)
        suggested_skills = [s.strip() for s in gap_matches[:3]]

        # Extract best-fit roles
        role_matches = re.findall(r"•\s+([A-Za-z][A-Za-z0-9 /]{3,40})\s+—", analysis)
        best_fit_roles = [r.strip() for r in role_matches[:4]]

        return {
            "analysis": analysis,
            "strength_score": min(max(strength_score, 0), 100),
            "suggested_skills": suggested_skills,
            "best_fit_roles": best_fit_roles,
        }
