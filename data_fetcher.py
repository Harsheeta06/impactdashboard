import requests
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

REPO_OWNER = "PostHog"
REPO_NAME = "posthog"


def fetch_posthog_data():
    url = "https://api.github.com/graphql"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}

    query = """
    query($owner: String!, $name: String!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        pullRequests(
          first: 100,
          after: $cursor,
          orderBy: {field: UPDATED_AT, direction: DESC},
          states: MERGED
        ) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            author { login }
            title
            createdAt
            mergedAt
            additions
            deletions
            url
            labels(first: 10) { nodes { name } }
            reviews { totalCount }
          }
        }
      }
    }
    """

    ninety_days_ago = datetime.utcnow() - timedelta(days=90)

    has_next_page = True
    cursor = None
    all_prs = []

    MAX_PRS = 1500  # safety cap

    print("🚀 Fetching PRs with pagination...")

    while has_next_page and len(all_prs) < MAX_PRS:
        variables = {
            "owner": REPO_OWNER,
            "name": REPO_NAME,
            "cursor": cursor
        }

        response = requests.post(
            url,
            json={"query": query, "variables": variables},
            headers=headers
        )

        if response.status_code != 200:
            print(f"❌ HTTP Error: {response.status_code}")
            return

        res_json = response.json()

        if "errors" in res_json:
            print(f"❌ GraphQL Error: {res_json['errors']}")
            return

        data = res_json["data"]["repository"]["pullRequests"]
        prs = data["nodes"]

        if not prs:
            break

        all_prs.extend(prs)

        has_next_page = data["pageInfo"]["hasNextPage"]
        cursor = data["pageInfo"]["endCursor"]

        print(f"Fetched {len(all_prs)} PRs so far...")

    print("🔍 Filtering to last 90 days...")

    filtered_prs = [
        pr for pr in all_prs
        if datetime.strptime(pr["mergedAt"], "%Y-%m-%dT%H:%M:%SZ") >= ninety_days_ago
    ]

    with open("posthog_data.json", "w") as f:
        json.dump(filtered_prs, f)

    print(f"✅ Done! Saved {len(filtered_prs)} PRs from last 90 days.")

    # ✅ Validation (VERY IMPORTANT)
    if filtered_prs:
        dates = [
            datetime.strptime(pr["mergedAt"], "%Y-%m-%dT%H:%M:%SZ")
            for pr in filtered_prs
        ]

        print("\n📊 VALIDATION:")
        print("Oldest PR:", min(dates))
        print("Newest PR:", max(dates))
        print("Total PRs:", len(filtered_prs))


if __name__ == "__main__":
    fetch_posthog_data()