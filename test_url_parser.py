import re
from typing import Optional, Tuple

# Copy of the fixed parse_repo_url function
def parse_repo_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Parses a Git repository URL to extract platform and a simplified repo identifier."""
    # Fixed regex pattern for GitHub URLs
    github_match = re.match(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+/[\w.-]+)(?:\.git)?/?$", url)
    if github_match:
        return "github", github_match.group(1)

    gitlab_match = re.match(r"^(?:https?://)?(?:www\.)?gitlab\.com/([\w.-]+(?:/[\w.-]+)+)(?:\.git)?/?$", url)
    if gitlab_match:
        return "gitlab", gitlab_match.group(1)
    return None, None

# Test URLs
test_urls = [
    "https://github.com/Slipstreamm/discordbot",
    "http://github.com/Slipstreamm/discordbot",
    "github.com/Slipstreamm/discordbot",
    "www.github.com/Slipstreamm/discordbot",
    "https://github.com/Slipstreamm/discordbot.git",
    "https://gitlab.com/group/project",
    "https://gitlab.com/group/subgroup/project",
    "invalid-url"
]

# Test each URL
print("Testing URL parsing with fixed regex pattern:")
print("-" * 50)
for url in test_urls:
    platform, repo_id = parse_repo_url(url)
    result = f"Valid: {platform}, {repo_id}" if platform else "Invalid URL"
    print(f"{url} => {result}")
