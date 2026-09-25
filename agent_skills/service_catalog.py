from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceGroup:
    slug: str
    label: str
    display_order: int
    selectable: bool = False


@dataclass(frozen=True)
class ServiceSkillProfile:
    slug: str
    label: str
    group_slug: str | None
    display_order: int
    intake_topics: tuple[str, ...]
    escalation_topics: tuple[str, ...] = ()
    version: str = "1.0.0"
    selectable: bool = True

    def build_instructions(self) -> str:
        intake = ", ".join(self.intake_topics)
        escalation = ", ".join(self.escalation_topics) or "the general safety policy"
        return (
            f"Selected service: {self.label} ({self.slug}). Ask only when "
            f"needed about: {intake}. Escalate for human review for: "
            f"{escalation}. Do not provide regulated technical, medical, "
            "legal, financial, or emergency advice. Collect facts and route "
            "the request safely."
        )


class ServiceCatalog:
    def __init__(self, groups, services):
        self._groups = tuple(groups)
        self._services = tuple(services)
        self._groups_by_slug = self._index(self._groups, "group")
        self._services_by_slug = self._index(self._services, "service")
        self._validate()

    @staticmethod
    def _index(items, kind):
        result = {}
        for item in items:
            if item.slug in result:
                raise ValueError(f"Duplicate {kind} slug: {item.slug}")
            result[item.slug] = item
        return result

    def _validate(self):
        overlap = set(self._groups_by_slug) & set(self._services_by_slug)
        if overlap:
            raise ValueError(f"Group and service slugs overlap: {sorted(overlap)}")
        for group in self._groups:
            if group.selectable:
                raise ValueError(f"Service group must not be selectable: {group.slug}")
        for profile in self._services:
            if not profile.selectable:
                raise ValueError(f"Service profile must be selectable: {profile.slug}")
            if profile.group_slug is not None and profile.group_slug not in self._groups_by_slug:
                raise ValueError(
                    f"Unknown group '{profile.group_slug}' for service '{profile.slug}'"
                )
            if not profile.intake_topics:
                raise ValueError(f"Service must define intake topics: {profile.slug}")

    def groups(self):
        return self._groups

    def services(self):
        return self._services

    def get(self, slug):
        try:
            return self._services_by_slug[slug]
        except KeyError as exc:
            raise KeyError(f"Service skill is not registered: {slug}") from exc

    def services_for_group(self, group_slug):
        if group_slug is not None and group_slug not in self._groups_by_slug:
            raise KeyError(f"Service group is not registered: {group_slug}")
        return tuple(p for p in self._services if p.group_slug == group_slug)


GROUPS = (
    ServiceGroup("home-services", "Home Services", 2),
    ServiceGroup("professional-services", "Professional Services", 3),
    ServiceGroup("automotive-root", "Automotive", 4),
    ServiceGroup("events-root", "Events", 5),
    ServiceGroup("other-root", "Other Services", 6),
    ServiceGroup("transport-tourism-root", "Transport & Tourism", 7),
)


COMMON = ("work or service required", "service location", "desired timing", "relevant constraints")


def profile(slug, label, group, order, topics=COMMON, escalation=()):
    return ServiceSkillProfile(slug, label, group, order, topics, escalation)


SERVICES = (
    # No parent is assigned to these 13 services because the supplied
    # taxonomy did not include the trades-group slug.
    profile("plumbing", "Plumbing", None, 1, ("issue or work required", "property location", "affected fixture", "when it started"), ("gas smell", "flooding", "sewage exposure")),
    profile("electrical", "Electrical", None, 2, ("issue or work required", "property location", "affected circuit or equipment", "power availability"), ("electric shock", "sparks or fire", "exposed live wiring")),
    profile("building", "Building & Construction", None, 3, ("project scope", "site location", "property type", "plans or approvals", "desired timing"), ("structural instability", "collapse risk", "regulated or high-value work")),
    profile("painting", "Painting", None, 4, ("areas and surfaces", "site location", "interior or exterior", "approximate size", "desired timing"), ("lead or asbestos concern", "unsafe access at height")),
    profile("roofing", "Roofing", None, 5, ("roof issue or work", "site location", "roof type", "damage extent", "access constraints"), ("major leak", "storm damage", "collapse risk", "unsafe work at height")),
    profile("renovation", "Renovation & Remodeling", None, 6, ("areas involved", "site location", "scope and goals", "plans or approvals", "target timing"), ("structural changes", "hazardous materials", "high-value work")),
    profile("hvac", "HVAC & Air Conditioning", None, 7, ("system type", "fault or requested work", "site location", "current behaviour", "preferred timing"), ("burning smell", "electrical hazard", "refrigerant concern")),
    profile("flooring", "Flooring", None, 8, ("flooring type", "install or repair", "site location", "approximate area", "subfloor condition")),
    profile("security", "Security & CCTV", None, 9, ("system type", "install or fault", "site location", "coverage required", "existing equipment"), ("active break-in", "personal safety threat", "privacy concern")),
    profile("carpentry", "Carpentry & Woodwork", None, 10, ("item or structure", "repair or new work", "site location", "materials or dimensions", "desired timing"), ("structural failure", "unsafe stairs or barriers")),
    profile("fencing", "Fencing & Gates", None, 11, ("fence or gate type", "repair or installation", "site location", "approximate length", "automation needs"), ("electrical gate hazard", "pool-safety barrier")),
    profile("tiling", "Tiling", None, 12, ("area to tile", "site location", "installation or repair", "approximate area", "tile availability"), ("water damage", "hazardous materials")),
    profile("welding", "Welding & Metal Works", None, 13, ("item or structure", "material", "repair or fabrication", "site location", "dimensions or drawings"), ("load-bearing failure", "fuel or gas container", "hot-work hazard")),

    profile("cleaning", "Cleaning", "home-services", 1, escalation=("biohazard", "hazardous chemicals", "crime scene")),
    profile("landscaping", "Landscaping & Gardening", "home-services", 2, escalation=("dangerous tree", "power-line proximity", "chemical exposure")),
    profile("pest-control", "Pest Control", "home-services", 3, ("pest or signs", "location", "affected areas", "when noticed", "children or pets present"), ("venomous animal", "severe infestation", "allergic reaction")),
    profile("moving", "Moving & Relocation", "home-services", 4, ("pickup and delivery locations", "move date", "property access", "inventory or volume", "special items"), ("hazardous goods", "extreme-value items")),
    profile("interior-design", "Interior Design", "home-services", 5),
    profile("waterproofing", "Waterproofing", "home-services", 6, escalation=("major water ingress", "structural damage", "mould or electrical exposure")),
    profile("curtains-blinds", "Curtains & Blinds", "home-services", 7),
    profile("furniture", "Furniture & Upholstery", "home-services", 8),
    profile("appliance-repair", "Appliance Repair", "home-services", 9, ("appliance type", "brand or model", "fault behaviour", "location", "error details"), ("gas smell", "electric shock", "smoke or fire", "refrigerant leak")),

    profile("photography", "Photography & Video", "professional-services", 1, ("event or subject", "location", "date and duration", "deliverables", "usage requirements"), ("restricted subject", "minor consent concern")),
    profile("videography", "Videography", "professional-services", 2, ("event or production", "location", "date and duration", "deliverables", "editing requirements"), ("restricted filming", "minor consent concern")),
    profile("it-services", "IT & Computer Services", "professional-services", 3, ("device or system", "issue or project", "location or remote access", "business impact", "operating environment"), ("cybersecurity incident", "data loss", "credential exposure", "regulated data")),
    profile("accounting", "Accounting", "professional-services", 4, ("service required", "jurisdiction", "individual or business", "relevant period", "deadline"), ("legal or tax dispute", "suspected fraud", "regulated financial advice")),
    profile("printing", "Printing & Signage", "professional-services", 5),
    profile("tutoring", "Tutoring & Education", "professional-services", 6, escalation=("child safeguarding concern", "assessment misconduct")),
    profile("health-wellness", "Health & Wellness", "professional-services", 7, ("service sought", "location or online", "goals", "availability", "accessibility needs"), ("medical emergency", "self-harm risk", "diagnosis or treatment request")),

    profile("automotive", "Automotive & Vehicle", "automotive-root", 0, escalation=("collision emergency", "fuel leak", "fire risk", "unsafe vehicle")),
    profile("mechanic", "Mechanic", "automotive-root", 1, ("vehicle make and model", "fault or service", "symptoms", "vehicle location", "drivability"), ("brake or steering failure", "fuel leak", "smoke or fire")),
    profile("car-detailing", "Car Detailing", "automotive-root", 2),
    profile("locksmith", "Locksmith", "automotive-root", 3, ("lock or key type", "property or vehicle", "location", "access situation", "proof of authority"), ("person locked in", "active break-in", "ownership ambiguity")),
    profile("windscreen", "Windscreen", "automotive-root", 4, escalation=("unsafe visibility", "shattered glass", "roadside danger")),

    profile("events", "Events & Entertainment", "events-root", 0, escalation=("crowd-safety concern", "regulated event", "high-value event")),
    profile("catering", "Catering & Food", "events-root", 1, ("event", "location", "date and guest count", "menu style", "allergies or dietary needs"), ("severe allergy", "food-safety complaint", "regulated alcohol service")),
    profile("entertainment", "Entertainment", "events-root", 2),
    profile("florist", "Florist", "events-root", 3),
    profile("event-planning", "Event Planning", "events-root", 4, escalation=("crowd-safety concern", "regulated event", "high-value commitments")),

    profile("other", "Other", "other-root", 1, escalation=("dangerous, illegal, regulated, or highly unusual work",)),

    profile("airport-transfers", "Airport & Hotel Transfers", "transport-tourism-root", 1, ("pickup and destination", "date and time", "passenger count", "flight details", "luggage or accessibility needs"), ("unaccompanied minor", "medical transport need")),
    profile("tour-bus", "Tour Bus & Coach", "transport-tourism-root", 2, escalation=("unsafe itinerary", "regulated passenger transport concern")),
    profile("taxi", "Taxi & Private Hire", "transport-tourism-root", 3, escalation=("unaccompanied minor", "medical emergency", "unsafe pickup conditions")),
    profile("boat-transport", "Boat & Water Transport", "transport-tourism-root", 4, escalation=("unsafe weather", "emergency transport", "dangerous goods", "regulated marine operation")),
    profile("bike-rental", "Motorbike & Scooter Rental", "transport-tourism-root", 5, escalation=("licence mismatch", "unsafe rider or vehicle condition")),
    profile("car-rental", "Car Rental", "transport-tourism-root", 6, escalation=("licence mismatch", "unsafe or unlawful use")),
    profile("tour-guide", "Tour Guide Services", "transport-tourism-root", 7, escalation=("unsafe itinerary", "restricted location", "vulnerable traveller concern")),
)


service_catalog = ServiceCatalog(GROUPS, SERVICES)
