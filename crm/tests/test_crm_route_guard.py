"""حارسٌ يعدّ مسارات `/api/platform/crm/` من الـURLconf الحقيقيّ — لا قائمةٌ يدويّة
تتقادم بصمت. عضوُ شركةٍ عاديّ والمجهول يُردّان على كلٍّ منها بلا استثناء."""
import re

from django.urls import get_resolver
from rest_framework.test import APIClient, APITestCase

from ._helpers import make_plain_user


def _crm_routes():
    def walk(patterns, prefix=""):
        for entry in patterns:
            route = prefix + str(entry.pattern)
            if hasattr(entry, "url_patterns"):
                yield from walk(entry.url_patterns, route)
            else:
                yield route

    routes = []
    for route in walk(get_resolver().url_patterns):
        route = route.replace("^", "").replace("$", "")
        if not route.startswith("api/platform/crm/"):
            continue
        if "format" in route:
            continue
        route = re.sub(r"<int:[^>]+>", "1", route)
        route = re.sub(r"<str:[^>]+>", "x", route)
        route = re.sub(r"\(\?P<\w+>[^)]*\)", "1", route)
        routes.append("/" + route)
    return sorted(set(routes))


class CrmRouteGuardTest(APITestCase):
    def test_every_crm_route_exists_and_is_closed_to_a_plain_member(self):
        routes = _crm_routes()
        self.assertGreaterEqual(len(routes), 10, f"عددُ مسارات CRM أقلّ من المتوقَّع: {routes}")

        client = APIClient()
        client.force_authenticate(user=make_plain_user())
        for route in routes:
            with self.subTest(route=route):
                response = client.get(route)
                self.assertEqual(
                    response.status_code, 403,
                    f"عضوٌ عاديٌّ وصل إلى {route} بحالة {response.status_code}",
                )

    def test_every_crm_route_is_closed_to_an_anonymous_visitor(self):
        client = APIClient()
        for route in _crm_routes():
            with self.subTest(route=route):
                response = client.get(route)
                self.assertIn(
                    response.status_code, (401, 403),
                    f"مجهولٌ وصل إلى {route} بحالة {response.status_code}",
                )
