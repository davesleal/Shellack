#!/usr/bin/env python3
"""
App Store Connect Integration
Fetches crash reports and customer feedback
"""

import os
import time
import jwt
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class AppStoreConnectClient:
    """Client for App Store Connect API"""

    BASE_URL = "https://api.appstoreconnect.apple.com/v1"

    def __init__(self, key_id: str, issuer_id: str, private_key_path: str):
        self.key_id = key_id
        self.issuer_id = issuer_id

        # Load private key
        with open(private_key_path, "r") as f:
            self.private_key = f.read()

    def _generate_token(self) -> str:
        """Generate JWT token for API authentication"""
        headers = {"alg": "ES256", "kid": self.key_id, "typ": "JWT"}

        payload = {
            "iss": self.issuer_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + 1200,  # 20 minutes
            "aud": "appstoreconnect-v1",
        }

        token = jwt.encode(
            payload, self.private_key, algorithm="ES256", headers=headers
        )

        return token

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make authenticated request to App Store Connect API"""
        token = self._generate_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = f"{self.BASE_URL}{endpoint}"
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        return response.json()

    def get_apps(self) -> List[Dict]:
        """Get all apps"""
        data = self._make_request("/apps")
        return data.get("data", [])

    def get_app_id_by_bundle_id(self, bundle_id: str) -> Optional[str]:
        """Get app ID by bundle identifier"""
        apps = self.get_apps()
        for app in apps:
            if app["attributes"]["bundleId"] == bundle_id:
                return app["id"]
        return None

    def get_customer_reviews(
        self, app_id: str, since: Optional[datetime] = None
    ) -> List[Dict]:
        """Get customer reviews for an app"""
        params = {}

        if since:
            params["filter[createdDate]"] = f"GTE_{since.isoformat()}"

        endpoint = f"/apps/{app_id}/customerReviews"
        data = self._make_request(endpoint, params=params)

        return data.get("data", [])

    def get_beta_feedback(
        self, app_id: str, since: Optional[datetime] = None
    ) -> List[Dict]:
        """Get TestFlight beta feedback"""
        params = {}

        if since:
            params["filter[createdDate]"] = f"GTE_{since.isoformat()}"

        endpoint = f"/apps/{app_id}/betaFeedback"

        try:
            data = self._make_request(endpoint, params=params)
            return data.get("data", [])
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Beta feedback endpoint not available
                return []
            raise

    def poll_for_new_feedback(
        self, bundle_id: str, callback, poll_interval: int = 300  # 5 minutes
    ):
        """
        Continuously poll for new feedback and invoke callback

        Args:
            bundle_id: App bundle identifier
            callback: Function to call with new feedback items
            poll_interval: Seconds between polls
        """
        app_id = self.get_app_id_by_bundle_id(bundle_id)
        if not app_id:
            raise ValueError(f"App not found: {bundle_id}")

        last_check = datetime.now() - timedelta(hours=24)

        print(f"📱 Polling for feedback on {bundle_id} (app_id: {app_id})")

        while True:
            try:
                # Get customer reviews
                reviews = self.get_customer_reviews(app_id, since=last_check)

                for review in reviews:
                    attrs = review["attributes"]
                    callback(
                        {
                            "type": "review",
                            "app_id": app_id,
                            "bundle_id": bundle_id,
                            "title": attrs.get("title", ""),
                            "body": attrs.get("body", ""),
                            "rating": attrs.get("rating", 0),
                            "created_date": attrs.get("createdDate", ""),
                            "reviewer_nickname": attrs.get(
                                "reviewerNickname", "Anonymous"
                            ),
                        }
                    )

                # Get beta feedback
                beta_feedback = self.get_beta_feedback(app_id, since=last_check)

                for feedback in beta_feedback:
                    attrs = feedback["attributes"]
                    callback(
                        {
                            "type": "beta_feedback",
                            "app_id": app_id,
                            "bundle_id": bundle_id,
                            "comment": attrs.get("comment", ""),
                            "created_date": attrs.get("createdDate", ""),
                            "email": attrs.get("email", "Anonymous"),
                        }
                    )

                last_check = datetime.now()

                print(
                    f"✅ Checked at {last_check.isoformat()} - Found {len(reviews)} reviews, {len(beta_feedback)} feedback"
                )

            except Exception as e:
                print(f"❌ Error polling: {str(e)}")

            time.sleep(poll_interval)


def format_feedback_for_slack(feedback: Dict) -> str:
    """Format feedback item for Slack message"""
    if feedback["type"] == "review":
        stars = "⭐" * feedback["rating"]
        return (
            f"📱 *New App Store Review*\n\n"
            f"*Rating:* {stars} ({feedback['rating']}/5)\n"
            f"*Title:* {feedback['title']}\n"
            f"*Review:* {feedback['body']}\n"
            f"*Reviewer:* {feedback['reviewer_nickname']}\n"
            f"*Date:* {feedback['created_date']}"
        )
    elif feedback["type"] == "beta_feedback":
        return (
            f"🧪 *New TestFlight Feedback*\n\n"
            f"*Comment:* {feedback['comment']}\n"
            f"*Tester:* {feedback['email']}\n"
            f"*Date:* {feedback['created_date']}"
        )
    else:
        return f"❓ Unknown feedback type: {feedback['type']}"


if __name__ == "__main__":
    # Test the integration
    client = AppStoreConnectClient(
        key_id=os.environ["APP_STORE_CONNECT_KEY_ID"],
        issuer_id=os.environ["APP_STORE_CONNECT_ISSUER_ID"],
        private_key_path=os.environ["APP_STORE_CONNECT_PRIVATE_KEY_PATH"],
    )

    # Get all apps
    apps = client.get_apps()
    print(f"Found {len(apps)} apps:")
    for app in apps:
        print(f"  - {app['attributes']['name']} ({app['attributes']['bundleId']})")
