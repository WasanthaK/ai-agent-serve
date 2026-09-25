import unittest

from agent_skills.service_catalog import (
    GROUPS,
    SERVICES,
    ServiceCatalog,
    ServiceGroup,
    ServiceSkillProfile,
    service_catalog,
)


class ServiceCatalogTests(unittest.TestCase):
    def test_catalogue_contains_expected_taxonomy(self):
        self.assertEqual(len(GROUPS), 6)
        self.assertEqual(len(SERVICES), 47)
        self.assertEqual(len({profile.slug for profile in SERVICES}), 47)

    def test_group_headers_are_not_selectable(self):
        self.assertTrue(all(not group.selectable for group in GROUPS))
        self.assertTrue(all(profile.selectable for profile in SERVICES))

    def test_exact_service_lookup(self):
        self.assertEqual(service_catalog.get("plumbing").label, "Plumbing")
        self.assertIsNone(service_catalog.get("plumbing").group_slug)
        self.assertIn("burning smell", service_catalog.get("hvac").escalation_topics)

    def test_group_lookup_excludes_header(self):
        profiles = service_catalog.services_for_group("home-services")
        self.assertEqual(len(profiles), 9)
        self.assertEqual(profiles[0].slug, "cleaning")
        self.assertEqual(profiles[-1].slug, "appliance-repair")

    def test_unknown_group_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            ServiceCatalog(
                (ServiceGroup("known", "Known", 1),),
                (ServiceSkillProfile("example", "Example", "missing", 1, ("scope",)),),
            )

    def test_selectable_group_is_rejected(self):
        with self.assertRaises(ValueError):
            ServiceCatalog((ServiceGroup("bad", "Bad", 1, selectable=True),), ())

    def test_domain_instructions_include_guardrails(self):
        instructions = service_catalog.get("health-wellness").build_instructions()
        self.assertIn("medical emergency", instructions)
        self.assertIn("Do not provide regulated", instructions)


if __name__ == "__main__":
    unittest.main()
