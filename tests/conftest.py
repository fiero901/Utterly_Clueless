"""Shared fixtures. All deterministic-layer tests use canned data (offline)."""
import pytest

# A small, stable slice of the real freehealth.mohp.gov.np bed-summary shape.
# Field names are the real feed keys (verified against the live API).
@pytest.fixture
def canned_beds():
    return [
        {"health_facility_name": "Tribhuvan University Teaching Hospital",
         "district_name": "Kathmandu", "palika_name": "Kathmandu",
         "public_nonpublic": "Public", "free_beds": "42",
         "total_beds_active": "520", "total_bed_capacity": "600",
         "contact_number": "01-4511111"},
        {"health_facility_name": "Nepal Army General Hospital",
         "district_name": "Kathmandu", "palika_name": "Kathmandu",
         "public_nonpublic": "Public", "free_beds": "9",
         "total_beds_active": "300", "total_bed_capacity": "350",
         "contact_number": "01-4416111"},
        {"health_facility_name": "Aakash Health Post",
         "district_name": "Kathmandu", "palika_name": "Gokul",
         "public_nonpublic": "Public", "free_beds": "2",
         "total_beds_active": "10", "total_bed_capacity": "12",
         "contact_number": "01-5512345"},
        {"health_facility_name": "Prime Teaching Hospital",
         "district_name": "Jhapa", "palika_name": "Dharan",
         "public_nonpublic": "Public", "free_beds": "55",
         "total_beds_active": "400", "total_bed_capacity": "450",
         "contact_number": "021-531111"},
    ]

