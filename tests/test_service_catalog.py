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
        self.assertEqual(len(GROUPS), 7)
        self.assertEqual(len(SERVICES), 47)
        self.assertEqual(len({profile.slug for profile in SERVICES}), 47)

    def test_group_headers_are_not_selectable(self):
        self.assertTrue(all(not group.selectable for group in GROUPS))
        self.assertTrue(all(profile.selectable for profile in SERVICES))

    def test_exact_service_lookup(self):
        self.assertEqual(service_catalog.get("plumbing").label, "Plumbing")
        self.assertEqual(service_catalog.get("plumbing").group_slug, "trades")
        self.assertIn("burning smell", service_catalog.get("hvac").escalation_topics)

    def test_group_lookup_excludes_header(self):
        profiles = service_catalog.services_for_group("home-services")
        self.assertEqual(len(profiles), 9)
        self.assertEqual(profiles[0].slug, "cleaning")
        self.assertEqual(profiles[-1].slug, "appliance-repair")

        trades = service_catalog.services_for_group("trades")
        self.assertEqual(len(trades), 13)
        self.assertEqual(trades[0].slug, "plumbing")
        self.assertEqual(trades[-1].slug, "welding")

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

    def test_analysis_instructions_include_each_profile_once(self):
        instructions = service_catalog.build_analysis_instructions()
        self.assertEqual(instructions.count("- plumbing:"), 1)
        self.assertEqual(instructions.count("- health-wellness:"), 1)
        self.assertIn("ask only for information required", instructions)

    def test_catalogue_serializes_for_api(self):
        result = service_catalog.as_dict()
        self.assertEqual(len(result["groups"]), 7)
        self.assertEqual(len(result["services"]), 47)
        self.assertFalse(result["groups"][0]["selectable"])
        self.assertTrue(result["services"][0]["selectable"])
        self.assertEqual(result["services"][0]["group_slug"], "trades")


if __name__ == "__main__":
    unittest.main()
