#!/usr/bin/env python3
"""
Needle-in-Haystack Experiment
==============================
Creates large, noisy source documents (each ~4000-6000 chars) with specific
facts buried deep inside irrelevant filler.  Tests whether gpt-4o + RAG can
extract the needles without being misled by the haystack.

The documents simulate a real 600GB network drive: meeting notes, policy
manuals, training materials, vendor correspondence, safety audits -- with
a few critical facts scattered across them.

Usage:
    export OPENAI_API_KEY="sk-..."
    export HYBRIDRAG_API_ENDPOINT="https://api.openai.com"
    export HYBRIDRAG_API_PROVIDER="openai"
    python tools/needle_haystack_experiment.py
"""
from __future__ import annotations

import copy
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from src.core.chunker import Chunker
from src.core.config import apply_mode_to_config, load_config
from src.core.embedder import Embedder
from src.core.llm_router import LLMRouter, invalidate_deployment_cache
from src.core.network_gate import configure_gate
from src.core.query_engine import QueryEngine
from src.core.query_mode import apply_query_mode_to_config
from src.core.vector_store import ChunkMetadata, VectorStore
from src.security.credentials import resolve_credentials

MARKER = "NIH"  # Needle In Haystack

# ---------------------------------------------------------------------------
# Large noisy documents with buried facts (needles)
# ---------------------------------------------------------------------------

TEST_DOCUMENTS = {
    # DOC 1: 80% meeting filler, needle buried in paragraph 7
    f"{MARKER}_Weekly_Staff_Meeting_Notes_Jan2025.txt": """
WEEKLY STAFF MEETING NOTES -- January 14, 2025
Location: Building 7, Conference Room B
Attendees: J. Mitchell, R. Vasquez, T. Chen, P. Okafor, L. Bergstrom

AGENDA ITEM 1: Holiday Schedule Review
Discussion centered on the remaining PTO balances from Q4. HR confirmed that
unused days roll over but cap at 240 hours. Several team members asked about
the new flexible Friday policy starting in February. Mitchell noted that the
pilot program covers Buildings 5-9 only, excluding the warehouse. Vasquez
mentioned that the parking garage closure on MLK day would require alternate
arrangements for night shift.

AGENDA ITEM 2: Cafeteria Menu Changes
The vendor contract with Aramark expires March 31. Procurement is evaluating
three replacement vendors. Taste tests will be held February 3-5 in the main
lobby. Okafor volunteered to coordinate the survey forms. Chen suggested
adding a vegan station based on the last employee satisfaction survey results.

AGENDA ITEM 3: Training Compliance
All staff must complete cybersecurity awareness training by January 31. As of
today, 67% completion rate. Bergstrom will send reminders to the 14 team
members who haven't started. The OSHA refresher is due by Q2.

AGENDA ITEM 4: Facilities Update
The HVAC system in Building 12 was inspected last week. Three rooftop units
need compressor replacement. Estimated cost is $47,500 for all three.
Bergstrom confirmed that the capital budget has $62,000 remaining for Q1.

AGENDA ITEM 5: IT Ticket Backlog
The help desk reported 143 open tickets, down from 189 last week. The printer
replacement project is 60% complete -- 18 of 30 new printers deployed.
Remaining 12 printers arrive next Tuesday.

AGENDA ITEM 6: Safety Incident Review
No recordable injuries in December. The near-miss report from December 19
(forklift/pedestrian close call in Bay 4) resulted in new floor markings
and a speed bump installation. Cost: $3,200.

AGENDA ITEM 7: Equipment Inventory Discrepancy
During the annual inventory audit, a discrepancy was found in the RF test
equipment pool. Specifically, spectrum analyzer serial number SA-9000-7742
was last calibrated on 2024-06-15 and is now 7 months overdue for its annual
calibration. Additionally, the inventory revealed that 3 units of connector
torque wrench model CTW-150 are missing from the Building 12 tool crib.
Mitchell authorized an immediate purchase order for replacement CTW-150
units at $847 each, total $2,541. The overdue SA-9000-7742 calibration was
escalated to the metrology lab with a target completion of January 31.

AGENDA ITEM 8: Parking Lot Resurfacing
Phase 2 of the parking lot resurfacing will begin February 10. Lots C and D
will be closed for approximately 3 weeks. Temporary parking available in the
overflow lot behind Building 3. Shuttle service will run 6 AM to 7 PM.

AGENDA ITEM 9: Next Meeting
Next weekly meeting: January 21 at 10:00 AM, same location.
Meeting adjourned at 11:47 AM.
""",

    # DOC 2: Vendor correspondence with one critical warranty detail buried
    f"{MARKER}_Vendor_Email_Chain_Acme_RF_2025.txt": """
From: Sarah.Kim@acme-rf.com
To: procurement@ourcompany.com
Date: February 3, 2025
Subject: RE: RE: RE: Quote Request -- RF Amplifier Modules

Hi Procurement Team,

Thank you for your patience as we finalized the updated pricing. Please find
below the revised quote for your FY2025 order:

STANDARD ITEMS:
- RFA-200 Low-Noise Amplifier (qty 20): $1,245 each = $24,900
- RFA-200 Mounting Kit (qty 20): $89 each = $1,780
- Shipping (freight, insured): $1,200
- SUBTOTAL: $27,880

We are offering a 7% volume discount for orders of 20+ units, bringing the
total to $25,928.40.

Lead time is 6-8 weeks from PO receipt. We recommend placing the order by
February 15 to ensure delivery before your Q2 maintenance window.

Regarding the RFA-200 performance specifications:
- Gain: 32 dB nominal
- Noise figure: 1.8 dB maximum
- Operating band: 2.3-2.6 GHz
- Supply voltage: 12V DC, 2.1A typical
- MTBF: 35,000 hours (MIL-HDBK-217F)
- Operating temperature: -20C to +55C

Please also note the following important warranty update that differs from
our standard terms: beginning with serial numbers manufactured after January
2025 (serial prefix RFA2025-), the warranty period has been extended from
the standard 24 months to 36 months. This applies ONLY to the RFA-200 model
and does not extend to accessories or mounting kits. The extended warranty
covers manufacturing defects and component failure under normal operating
conditions but excludes damage from lightning, surge events, or operation
outside the specified temperature range.

Separately, I wanted to follow up on the field failure report you sent in
December regarding two RFA-200 units (serial RFA2024-0847 and RFA2024-0851).
Our engineering team completed root cause analysis and determined that both
failures were caused by condensation-related corrosion at the RF output
connector. This failure mode is consistent with installations where the
environmental seal was not properly seated. We recommend applying the
updated installation procedure (Tech Bulletin TB-2025-003) to all deployed
units during the next scheduled maintenance cycle.

Let me know if you need anything else. Happy to set up a call to discuss
the field failure analysis in more detail.

Best regards,
Sarah Kim
Senior Account Manager
Acme RF Solutions

---
PREVIOUS MESSAGES IN THREAD (summarized):
- Jan 12: Initial RFQ sent by our procurement
- Jan 18: Acme provided preliminary pricing ($1,320/unit before discount)
- Jan 22: We requested volume pricing for 20+ units
- Jan 28: Acme asked for delivery timeline preferences
""",

    # DOC 3: Safety audit with one critical finding buried in page 3
    f"{MARKER}_Annual_Safety_Audit_Report_2024.txt": """
ANNUAL SAFETY AUDIT REPORT -- 2024
Prepared by: Environmental Health & Safety Division
Report Number: EHS-2024-AR-017
Date: December 15, 2024

EXECUTIVE SUMMARY:
The 2024 annual safety audit covered 14 facilities across the Eastern Region.
Overall safety compliance improved from 87.3% in 2023 to 91.2% in 2024.
Zero fatalities, three recordable injuries (two ergonomic, one laceration),
and 47 near-miss reports were documented during the audit period.

SECTION 1: FIRE SAFETY
All 14 facilities passed fire suppression system inspections. Fire
extinguisher compliance was 98.7% (3 extinguishers out of date at
Building 9). Emergency evacuation drills were conducted quarterly at all
sites. Average evacuation time improved from 4.2 minutes to 3.8 minutes.
Sprinkler system flow tests met NFPA 25 requirements at all locations.

SECTION 2: ELECTRICAL SAFETY
Arc flash hazard assessments were completed at Buildings 1-6 and 10-14.
Buildings 7-9 are scheduled for Q1 2025. Lockout/tagout compliance was
94.1%. Eight minor discrepancies were found: six missing labels and two
expired locks. All corrected within 48 hours. Ground fault circuit
interrupter (GFCI) testing: 412 of 418 outlets passed (98.6%). Six
failures found in Building 5 break room and Building 11 loading dock --
replaced same day.

SECTION 3: CHEMICAL SAFETY AND HAZMAT
Chemical inventory verification completed at all sites. SDS (Safety Data
Sheet) accessibility confirmed via the digital kiosk system. One finding
of note: Building 12, Room 127 (the electronics repair lab) was found to
have 14 containers of IPA (isopropyl alcohol 99%) stored above the
NFPA threshold of 10 gallons in a single room without a flammable
storage cabinet. This represents a CLASS II VIOLATION. Corrective action:
a 45-gallon Justrite flammable storage cabinet (model 894500, rated for
Class IB liquids) was procured and installed by December 22, 2024. Cost:
$1,847. The excess IPA was redistributed to Buildings 3 and 7 where
consumption rates are higher. Re-inspection confirmed compliance on
December 28.

Additionally, the spill response kit inventory showed that 3 of 14
facilities were missing absorbent booms (Buildings 2, 8, and 13).
Replacements were ordered and received by December 10.

SECTION 4: ERGONOMICS
Ergonomic assessments were performed for 287 workstations. 23 required
adjustments (8.0%), down from 31 in 2023 (10.8%). Most common issues:
monitor height, chair adjustment, and keyboard tray position. All
adjustments were made within 2 weeks of assessment.

SECTION 5: PPE COMPLIANCE
PPE compliance was audited via random spot checks (847 observations
across all sites). Compliance rate: 96.3% (31 observations with
missing or improperly worn PPE). Most common violation: safety glasses
not worn in designated areas (19 of 31 observations). Training
refreshers were scheduled for the affected teams.

SECTION 6: FALL PROTECTION
All elevated work platforms inspected. Three guardrail deficiencies
found at Building 6 mezzanine (loose mounting bolts). Repaired same
day. Harness inspection records were 100% current for all authorized
climbers. Ladder inspection: 7 of 194 ladders failed (bent rungs,
missing feet, exceeded load rating). All removed from service and
replaced.

SECTION 7: RECOMMENDATIONS
1. Complete arc flash assessments for Buildings 7-9 (Q1 2025)
2. Increase chemical storage audits to quarterly for Building 12
3. Add slip-resistant mats at Building 5 loading dock entrance
4. Replace aging fire alarm panels at Buildings 1 and 2 (20+ years old)
5. Expand forklift pedestrian awareness training to warehouse staff

AUDITOR NOTES:
This was the third consecutive year of improvement. The safety culture
initiative launched in 2022 continues to show measurable results.
Regional management should be commended for sustained engagement.
""",

    # DOC 4: Training manual with one specific config value buried in noise
    f"{MARKER}_IT_Onboarding_Manual_v3.txt": """
IT DEPARTMENT ONBOARDING MANUAL -- Version 3.0
Last Updated: October 2024
Department: Information Technology Services

CHAPTER 1: WELCOME TO IT

Welcome to the Information Technology Services department. This manual
covers everything you need to know during your first 90 days. Please
read each section carefully and complete the checklist at the end.

Your first week will include:
- Badge activation and building access setup (see Security, Building 7)
- Laptop provisioning (allow 2-3 business days)
- VPN setup and remote access configuration
- Introduction to the help desk ticketing system
- Meet-and-greet with your team lead

CHAPTER 2: ACCEPTABLE USE POLICY (Summary)

All company IT resources are provided for business use. Limited personal
use is acceptable during breaks, provided it does not violate company
policies. You must not install unapproved software. The list of approved
software is maintained on the intranet at /it/approved-software. All
internet traffic is monitored and logged. USB drives must be encrypted
using BitLocker. Personal devices may connect to the guest WiFi network
(SSID: GUEST-VISITOR) but must not connect to the corporate network.

CHAPTER 3: NETWORK INFRASTRUCTURE

Our corporate network spans 14 buildings across the campus. The backbone
uses 10 Gbps fiber links between core switches in Buildings 1, 7, and 12.
Edge switches in each building provide 1 Gbps copper to desktops and
802.11ax WiFi access points (approximately 340 APs campus-wide).

The data center is located in Building 1, Lower Level. It houses 48 rack
units across 6 cabinets. Power is supplied by redundant 100 kVA UPS
systems with 45-minute battery runtime at current load. Generator backup
provides indefinite runtime with 500-gallon diesel tank (approximately
72 hours at full load).

CHAPTER 4: VPN AND REMOTE ACCESS

Remote users connect via the Cisco AnyConnect client to vpn.internal.corp
on port 443. Split tunneling is disabled for security. The VPN
concentrator supports up to 500 concurrent sessions. Current peak usage
is approximately 280 simultaneous connections (typically between 9-10 AM
on Mondays). Authentication requires both Active Directory credentials
and Duo MFA (push notification or TOTP code).

CHAPTER 5: BACKUP AND DISASTER RECOVERY

All file servers are backed up nightly to the off-site facility in
Building 22 (the remote disaster recovery site located 12 miles from
campus). Backup retention policy: daily backups retained for 30 days,
weekly backups retained for 12 weeks, monthly backups retained for
13 months. Full system restore has been tested quarterly; last
successful test was September 15, 2024 (RTO achieved: 4 hours 12
minutes, target RTO: 8 hours).

CRITICAL: The disaster recovery site network peering uses a dedicated
dark fiber pair on a separate physical path from the primary WAN
connection. The failover circuit capacity is 1 Gbps, which is 10% of
the primary backbone. During a DR activation, non-essential services
(guest WiFi, video streaming, print services) are automatically shed
to preserve bandwidth for critical applications. The DR activation
procedure requires authorization from two of the following: CIO, IT
Director, or Network Operations Manager. The authorization code for
Q1 2025 is DR-AUTH-7749-ECHO. This code rotates quarterly.

CHAPTER 6: SERVICE DESK PROCEDURES

Log all incidents in ServiceNow. Priority levels:
- P1 (Critical): Total outage affecting > 50 users. Response: 15 min.
- P2 (High): Major degradation affecting a department. Response: 1 hour.
- P3 (Medium): Individual user impact. Response: 4 hours.
- P4 (Low): Enhancement request. Response: 3 business days.

Escalation path: Help Desk Analyst -> Team Lead -> IT Manager -> Director.

CHAPTER 7: HARDWARE STANDARDS

Standard desktop: Dell OptiPlex 7020, i7-13700, 32 GB RAM, 512 GB NVMe.
Standard laptop: Dell Latitude 5540, i7-1365U, 16 GB RAM, 512 GB NVMe.
Engineering workstation: Dell Precision 7875, Threadripper PRO, 128 GB
RAM, 2 TB NVMe, NVIDIA RTX A5000 (24 GB VRAM). Refresh cycle: 4 years
for desktops and laptops, 5 years for workstations.

CHAPTER 8: FIRST 90 DAYS CHECKLIST

[ ] Complete security training (Week 1)
[ ] Set up MFA on all accounts (Week 1)
[ ] Read and sign Acceptable Use Policy (Week 1)
[ ] Complete ITIL Foundations overview (Week 2-3)
[ ] Shadow senior analyst for 5 tickets (Week 2-4)
[ ] Complete VPN troubleshooting lab (Week 3)
[ ] Pass network fundamentals quiz (Week 4)
[ ] First solo P3 ticket resolution (Week 4-6)
[ ] Complete backup/restore procedure walkthrough (Week 6-8)
[ ] 90-day review with manager (Week 12)
""",

    # DOC 5: Project status report with one critical date hidden in updates
    f"{MARKER}_Project_Status_Update_Q1_2025.txt": """
PROJECT PORTFOLIO STATUS UPDATE -- Q1 2025
Prepared by: Program Management Office
Distribution: Senior Leadership, Department Heads
Date: March 15, 2025

PROJECT 1: ERP MIGRATION (PHASE 2)
Status: GREEN
Budget: $2.4M allocated, $1.1M spent to date
Timeline: On track for June 30 go-live
Team: 12 internal + 8 vendor FTEs
Notes: User acceptance testing begins April 7. Training schedule finalized
for all 340 end users across finance, HR, and procurement modules. Data
migration from legacy system completed January 28 with 99.7% record
accuracy. Three remaining data quality issues under investigation.

PROJECT 2: CAMPUS SECURITY CAMERA UPGRADE
Status: YELLOW
Budget: $890K allocated, $410K spent
Timeline: 2 weeks behind due to supply chain delays on PTZ cameras
Team: 4 internal + 6 vendor
Notes: 78 of 142 cameras installed. Remaining 64 cameras (Axis P3265-LVE
model) on backorder, ETA March 28. Temporary analog cameras deployed at
critical locations (main entrances, parking structures). The new NVR
storage array was delivered and racked but not yet configured.

PROJECT 3: WAREHOUSE AUTOMATION PILOT
Status: GREEN
Budget: $175K allocated, $42K spent
Timeline: On track for April pilot launch
Team: 3 internal
Notes: Six AGV (automated guided vehicle) units delivered January 15.
Programming and path mapping in progress. Safety zone configuration
requires coordination with EHS for pedestrian exclusion areas.

PROJECT 4: FIBER BACKBONE UPGRADE (BUILDINGS 7-9)
Status: RED
Budget: $340K allocated, $285K spent (84% consumed with 40% work remaining)
Timeline: Originally due March 31, now projected May 15
Team: 2 internal + 4 vendor
Notes: Budget overrun caused by unexpected asbestos abatement required in
Building 8 cable runs (cost: $67,000, not in original scope). Engineering
change order #ECO-2025-017 submitted for additional $95,000. Approval
pending from VP of Operations. CRITICAL: if ECO is not approved by
March 22, 2025, the project will miss the summer maintenance window and
slip to Q4 2025 -- a 6-month delay. The fiber vendor (NetWave
Communications) has a hard crew availability constraint: they must begin
the Building 9 pull by April 10 or they cannot return until October due
to a prior commitment with the city municipal network project.

PROJECT 5: EMPLOYEE WELLNESS APP
Status: GREEN
Budget: $45K allocated, $28K spent
Timeline: Launched February 1
Team: 2 internal
Notes: 412 of 1,200 employees registered (34.3% adoption). Target is 50%
by June 30. Push notification feature added in February update. Integration
with the health insurance portal is planned for Q3.

PROJECT 6: DATA CENTER COOLING OPTIMIZATION
Status: GREEN
Budget: $125K allocated, $88K spent
Timeline: Phase 1 complete, Phase 2 starts April
Team: 2 internal + 1 vendor
Notes: Hot aisle containment installed in Rows A-D. PUE improved from 1.72
to 1.51. Phase 2 will add variable speed fans and liquid cooling for the
GPU compute cluster. Expected additional PUE improvement to 1.38.

PROJECT 7: PRINT MANAGEMENT CONSOLIDATION
Status: GREEN
Budget: $52K allocated, $31K spent
Timeline: On track for April 30 completion
Team: 1 internal + 1 vendor
Notes: 18 of 30 new multifunction printers deployed (same as IT ticket
update from January). User training on FollowMe printing started March 3.
Paper consumption already down 22% since October baseline.

PORTFOLIO SUMMARY:
- 7 active projects, 5 Green, 1 Yellow, 1 Red
- Total portfolio budget: $4.027M, $1.985M spent (49.3%)
- Staffing: 26 internal + 20 vendor FTEs
- Key risk: Fiber backbone budget overrun (Project 4)
- Key decision needed: ECO-2025-017 approval by March 22
""",

    # DOC 6: Dense policy document with one specific number buried in legalese
    f"{MARKER}_Travel_Expense_Policy_Rev12.txt": """
CORPORATE TRAVEL AND EXPENSE POLICY -- Revision 12
Effective Date: January 1, 2025
Approved by: Chief Financial Officer
Policy Number: FIN-POL-2025-008

SECTION 1: PURPOSE AND SCOPE
This policy governs all business travel and expense reimbursement for
employees, contractors, and authorized travelers acting on behalf of the
company. All travel must be pre-approved by the traveler's direct manager
and, for trips exceeding $5,000 in estimated total cost, by the department
VP. International travel requires additional approval from the CFO's office
and a completed Travel Risk Assessment form (FIN-FORM-TR-001).

SECTION 2: BOOKING PROCEDURES
All domestic flights must be booked through Concur Travel at least 14 days
in advance. Economy class is the default for flights under 4 hours.
Business class may be approved for flights over 6 hours if the traveler
has a medical accommodation or will be presenting at a customer site
within 4 hours of landing. First class is not reimbursable under any
circumstances unless pre-approved in writing by the CEO.

SECTION 3: LODGING
Hotel reservations should be made through the company's preferred vendor
program (currently Marriott, Hilton, and IHG). Maximum per-night rate
without VP approval: $225 for Tier 1 cities (New York, San Francisco,
Boston, Washington DC, Los Angeles, Chicago, Seattle), $175 for Tier 2
cities, $135 for all other locations. Extended stay (over 5 consecutive
nights) requires a cost comparison with corporate apartment options.

SECTION 4: MEALS AND INCIDENTALS
Per diem rates follow the current GSA schedule. In lieu of per diem,
actual expenses may be claimed with itemized receipts. Alcohol is not
reimbursable except when entertaining a client, in which case the
Hospitality Entertainment Form (FIN-FORM-HE-002) must be submitted with
the expense report. Tips are reimbursable up to 20% of the pre-tax meal
amount. Room service charges exceeding $50 per meal require a written
justification.

SECTION 5: GROUND TRANSPORTATION
Rental cars must be mid-size or smaller unless traveling with 3+ persons
or transporting equipment. GPS and fuel pre-pay options should be
declined. Personal vehicle mileage is reimbursed at the IRS standard rate
(currently $0.67 per mile for 2025). Ride-share services (Uber, Lyft)
are permitted for trips under 30 miles. For trips exceeding 30 miles,
a rental car is typically more cost-effective and should be used instead.

SECTION 6: EXPENSE REPORTING
All expense reports must be submitted within 15 business days of trip
completion. Reports submitted after 30 days will be rejected without
exception. Receipts are required for all expenses over $25. Corporate
card transactions are automatically imported into Concur but still
require proper categorization and trip association.

SECTION 7: NON-TRAVEL EXPENSES
Office supplies under $100 may be purchased without pre-approval.
Equipment purchases between $100 and $2,500 require manager approval.
Equipment over $2,500 requires a purchase order through Procurement.
Conference registration fees are covered if the event is on the
approved professional development list. Maximum annual conference
budget per employee: $3,500.

SECTION 8: EXCEPTIONS AND SPECIAL CIRCUMSTANCES
The Chief Financial Officer may grant exceptions to any provision in
this policy on a case-by-case basis. Exception requests must be
submitted in writing via FIN-FORM-EX-003 at least 10 business days
before the planned expense. Emergency exceptions may be granted
verbally by the CFO and documented retroactively within 48 hours.

Note: Effective March 1, 2025, all international expense reports
exceeding $10,000 total are subject to a mandatory 15-business-day
audit hold before reimbursement processing. This change was implemented
following the discovery of duplicate reimbursement incident #FIN-INC-
2024-0194 (total overpayment: $23,847, recovered in full). The audit
hold applies regardless of traveler seniority or approval chain.

SECTION 9: VIOLATIONS
Violations of this policy may result in delayed reimbursement, required
repayment, or disciplinary action up to and including termination.
Fraudulent expense claims will be reported to the company's legal
department and may be referred to law enforcement.

REVISION HISTORY:
- Rev 12 (2025-01-01): Added international audit hold, updated mileage rate
- Rev 11 (2024-07-01): Updated hotel rate tiers
- Rev 10 (2024-01-01): Added ride-share guidelines
""",

    # DOC 7: Lengthy maintenance log with one anomalous reading hidden
    f"{MARKER}_HVAC_Maintenance_Log_Building12_2025.txt": """
HVAC MAINTENANCE LOG -- BUILDING 12
Year: 2025
Technician: R. Dominguez
System: Trane Intellipak 150-ton RTU (3 units: RTU-12A, RTU-12B, RTU-12C)

JANUARY INSPECTION (01/08/2025)
RTU-12A: All parameters normal. Supply air temp: 54.2F. Return air: 72.1F.
Refrigerant pressures: suction 68 psi, discharge 215 psi. Compressor
current draw: 78.3A (rated 85A). Economizer damper cycling properly.
Filter condition: clean (replaced December 15). Belt tension checked OK.
Condensate drain clear. No unusual noise or vibration.

RTU-12B: All parameters normal. Supply air temp: 53.8F. Return air: 71.8F.
Refrigerant pressures: suction 69 psi, discharge 218 psi. Compressor
current draw: 80.1A. Economizer damper cycling properly. Filter replaced
(was at 0.42 in. w.g., threshold 0.50). Belt tension adjusted (was
slightly loose). Condensate drain clear.

RTU-12C: All parameters normal. Supply air temp: 55.1F. Return air: 72.4F.
Refrigerant pressures: suction 67 psi, discharge 212 psi. Compressor
current draw: 76.9A. Economizer functioning. Filters clean. All belts good.

Building zone temperatures: all 23 zones within setpoint +/- 2F.
Energy consumption (December): 42,180 kWh. Trending normal for winter.

FEBRUARY INSPECTION (02/12/2025)
RTU-12A: Normal. Supply: 54.5F, Return: 71.9F. Suction: 67 psi, Discharge:
214 psi. Current: 79.0A. No issues.

RTU-12B: Normal. Supply: 54.1F, Return: 72.0F. Suction: 68 psi, Discharge:
216 psi. Current: 80.4A. Filter condition good.

RTU-12C: Normal. Supply: 54.8F, Return: 72.2F. Suction: 68 psi, Discharge:
213 psi. Current: 77.2A. All good.

Building zones: all within spec. Energy: 39,850 kWh (lower due to milder Feb).

MARCH INSPECTION (03/11/2025)
RTU-12A: Normal. Supply: 53.9F, Return: 71.5F. Suction: 69 psi, Discharge:
217 psi. Current: 78.8A. Economizer operating more frequently as outdoor
temps increase. Filter condition good.

RTU-12B: ANOMALY NOTED. Supply air temp: 58.3F (elevated from normal 54F
range). Return air: 72.1F. Suction pressure: 72 psi (slightly high).
Discharge: 224 psi (slightly high). Compressor current: 83.7A (approaching
rated 85A limit). Root cause investigation: found refrigerant charge
slightly low -- likely slow leak at the service valve on circuit 2. Added
1.5 lbs R-410A. Post-charge readings: Supply 54.4F, Suction 69 psi,
Discharge 216 psi, Current 80.0A. Will monitor monthly. Noted serial
number of suspect valve: TRANE-SV-2019-4481. If leak recurs, valve
replacement estimated at $2,200 parts + $800 labor.

RTU-12C: Normal. Supply: 55.0F, Return: 72.3F. Suction: 67 psi, Discharge:
211 psi. Current: 76.5A. All belts and filters good.

Building zones: Zone 14 (server room adjacent) was 68.1F, 1.9F below
setpoint. Adjusted damper position. All other zones within spec.
Energy: 38,420 kWh.

APRIL INSPECTION (04/09/2025) -- scheduled, not yet performed.
""",
}

# ---------------------------------------------------------------------------
# Needle queries -- each targets one specific buried fact
# ---------------------------------------------------------------------------

NEEDLE_QUERIES = [
    # Needle 1: SA-9000-7742 calibration overdue, buried in meeting notes agenda item 7
    {
        "q": "What is the calibration status of spectrum analyzer SA-9000-7742?",
        "needle": "Last calibrated 2024-06-15, 7 months overdue for annual calibration",
        "expected_facts": ["SA-9000-7742", "2024-06-15", "overdue"],
        "doc": "Weekly Staff Meeting Notes",
        "depth": "agenda item 7 of 9 (78% deep)",
    },
    # Needle 2: CTW-150 torque wrench missing, same meeting notes
    {
        "q": "How many CTW-150 torque wrenches are missing and what was the replacement cost?",
        "needle": "3 units missing, $847 each, total $2,541",
        "expected_facts": ["3", "847", "2,541"],
        "doc": "Weekly Staff Meeting Notes",
        "depth": "agenda item 7 of 9",
    },
    # Needle 3: RFA-200 warranty extension, buried in vendor email
    {
        "q": "What is the warranty period for RFA-200 units manufactured after January 2025?",
        "needle": "Extended from 24 months to 36 months for serial prefix RFA2025-",
        "expected_facts": ["36", "RFA2025"],
        "doc": "Vendor Email Chain",
        "depth": "paragraph 5 of 7 in email body",
    },
    # Needle 4: IPA storage violation, buried in safety audit section 3
    {
        "q": "What chemical storage violation was found at Building 12?",
        "needle": "14 containers IPA above NFPA 10-gallon threshold, CLASS II VIOLATION",
        "expected_facts": ["14", "IPA", "CLASS II"],
        "doc": "Annual Safety Audit",
        "depth": "section 3 of 7",
    },
    # Needle 5: DR authorization code, buried deep in IT onboarding manual
    {
        "q": "What is the disaster recovery authorization code for Q1 2025?",
        "needle": "DR-AUTH-7749-ECHO, rotates quarterly",
        "expected_facts": ["DR-AUTH-7749-ECHO"],
        "doc": "IT Onboarding Manual",
        "depth": "chapter 5 of 8",
    },
    # Needle 6: Fiber project ECO deadline, buried in project status
    {
        "q": "What is the deadline for approving ECO-2025-017 and what happens if missed?",
        "needle": "Must be approved by March 22, 2025 or 6-month delay to Q4",
        "expected_facts": ["March 22", "ECO-2025-017"],
        "doc": "Project Status Update",
        "depth": "project 4 of 7",
    },
    # Needle 7: Duplicate reimbursement incident amount, buried in policy
    {
        "q": "What was the total overpayment amount in the duplicate reimbursement incident?",
        "needle": "$23,847, incident FIN-INC-2024-0194, recovered in full",
        "expected_facts": ["23,847", "FIN-INC-2024-0194"],
        "doc": "Travel Expense Policy",
        "depth": "section 8 of 9",
    },
    # Needle 8: HVAC refrigerant leak valve serial, buried in March entry
    {
        "q": "What is the serial number of the suspect valve on RTU-12B and what is the repair estimate?",
        "needle": "TRANE-SV-2019-4481, $2,200 parts + $800 labor = $3,000 total",
        "expected_facts": ["TRANE-SV-2019-4481", "2,200"],
        "doc": "HVAC Maintenance Log",
        "depth": "March entry (3rd of 4 months)",
    },
    # CROSS-DOC SYNTHESIS: requires combining info from multiple noisy docs
    {
        "q": "What equipment issues were found during inspections across all documents in early 2025?",
        "needle": "Multi-doc: SA-9000 overdue cal, CTW-150 missing, RTU-12B refrigerant leak, camera supply delay, GFCI failures",
        "expected_facts": ["SA-9000", "RTU-12B"],
        "doc": "Multiple",
        "depth": "cross-document",
    },
    # DISTRACTOR: query that sounds like it could match but has no answer
    {
        "q": "What was the fire suppression system failure at Building 12?",
        "needle": "NONE -- all 14 facilities PASSED fire suppression inspections",
        "expected_facts": [],
        "expected_refuse": True,
        "doc": "Safety Audit (distractor)",
        "depth": "tests refusal when nearby data exists but answer doesn't",
    },
]


# ---------------------------------------------------------------------------
# Reuse indexing and scoring from sweet spot experiment
# ---------------------------------------------------------------------------

REFUSAL_PHRASES = [
    "not found", "no relevant", "no information", "does not contain",
    "no mention", "no data", "cannot answer", "no specific",
    "is not present", "not available", "no failure", "no fire",
    "passed", "no record of a failure", "no fire suppression.*failure",
]

SETTINGS_TO_TEST = [
    {"name": "STRICT-9",   "grounding_bias": 9, "allow_open_knowledge": False, "temperature": 0.03},
    {"name": "BALANCED-6", "grounding_bias": 6, "allow_open_knowledge": True,  "temperature": 0.15},
]


def index_corpus(config, embedder, store):
    """Index the noisy test documents."""
    chunker = Chunker(config.chunking)
    now = datetime.now(timezone.utc).isoformat()
    total = 0
    for filename, content in TEST_DOCUMENTS.items():
        fake_path = "EXPERIMENT_NIH/" + filename
        existing = store.get_file_hash(fake_path)
        chash = "{}:0".format(len(content))
        if existing == chash:
            print("  [SKIP] {} (already indexed)".format(filename))
            continue
        if existing:
            store.delete_chunks_by_source(fake_path)
        chunks = chunker.chunk_text(content.strip())
        if not chunks:
            continue
        embeddings = embedder.embed_batch(chunks)
        metadata = [
            ChunkMetadata(
                source_path=fake_path, chunk_index=i, text_length=len(c),
                created_at=now, access_tags=("shared",),
                access_tag_source="default_document_tags",
            ) for i, c in enumerate(chunks)
        ]
        store.add_embeddings(embeddings=embeddings, metadata_list=metadata,
                             texts=chunks, file_hash=chash)
        total += len(chunks)
        print("  [OK] {} -> {} chunks".format(filename, len(chunks)))
    return total


def run_experiment():
    config = load_config()
    apply_mode_to_config(config, "online")
    config.api.max_tokens = 2048
    creds = resolve_credentials(config, use_cache=False)
    if not creds.is_online_ready:
        print("[FAIL] No credentials")
        sys.exit(1)
    configure_gate(mode="online", api_endpoint=creds.endpoint)
    store = VectorStore(config.paths.database)
    embedder = Embedder(dimension=768)

    print("=" * 70)
    print("NEEDLE-IN-HAYSTACK EXPERIMENT")
    print("=" * 70)
    n = index_corpus(config, embedder, store)
    print("[OK] {} new chunks indexed".format(n))
    print()

    all_results = []
    total_cost = 0.0

    for setting in SETTINGS_TO_TEST:
        config.query.grounding_bias = setting["grounding_bias"]
        config.query.allow_open_knowledge = setting["allow_open_knowledge"]
        config.api.temperature = setting["temperature"]
        apply_query_mode_to_config(config)
        invalidate_deployment_cache()
        router = LLMRouter(config, credentials=creds)
        engine = QueryEngine(config, store, embedder, router)

        print("--- {} (bias={}, open={}, temp={}) ---".format(
            setting["name"], setting["grounding_bias"],
            setting["allow_open_knowledge"], setting["temperature"]))

        found = 0
        missed = 0

        for qi, nq in enumerate(NEEDLE_QUERIES):
            t0 = time.time()
            result = engine.query(nq["q"])
            answer = getattr(result, "answer", "")
            sources = getattr(result, "sources", [])
            cost = getattr(result, "cost_usd", 0) or 0
            latency = (time.time() - t0) * 1000
            total_cost += cost

            expected_refuse = nq.get("expected_refuse", False)
            is_refused = any(p in answer.lower() for p in REFUSAL_PHRASES)
            facts = nq.get("expected_facts", [])
            hits = sum(1 for f in facts if f.lower() in answer.lower()) if facts else 0

            if expected_refuse:
                ok = is_refused or any(
                    p in answer.lower()
                    for p in ["passed", "no failure", "all.*passed", "no fire"]
                )
                status = "PASS (correct refusal/negation)" if ok else "FAIL (hallucinated)"
            elif facts:
                ok = hits == len(facts)
                status = "FOUND {}/{} facts".format(hits, len(facts))
            else:
                ok = len(answer) > 100
                status = "ANSWERED ({} chars)".format(len(answer))

            if ok and not expected_refuse:
                found += 1
            elif not ok and not expected_refuse:
                missed += 1

            symbol = "+" if ok else "-"
            print("  {} Q{:02d} [{}] depth={}".format(
                symbol, qi + 1, status, nq["depth"][:30]))
            print("        needle: {}".format(nq["needle"][:70]))
            short = answer[:180].replace("\n", " ")
            print("        answer: {}".format(short))
            if not ok and facts:
                missing = [f for f in facts if f.lower() not in answer.lower()]
                print("        MISSING: {}".format(missing))
            print()

            all_results.append({
                "config": setting["name"], "question": nq["q"],
                "found": ok, "fact_hits": hits, "fact_total": len(facts),
                "refused": is_refused, "expected_refuse": expected_refuse,
                "answer_len": len(answer), "sources": len(sources),
                "latency_ms": latency, "depth": nq["depth"],
                "doc": nq["doc"],
            })

        total_q = len([q for q in NEEDLE_QUERIES if not q.get("expected_refuse")])
        print("  NEEDLE RETRIEVAL: {}/{} found, {}/{} missed".format(
            found, total_q, missed, total_q))
        print()

    # Summary
    print("=" * 70)
    print("NEEDLE-IN-HAYSTACK SUMMARY")
    print("=" * 70)
    for setting in SETTINGS_TO_TEST:
        cr = [r for r in all_results if r["config"] == setting["name"]]
        needles = [r for r in cr if not r["expected_refuse"]]
        distractors = [r for r in cr if r["expected_refuse"]]
        needle_found = sum(1 for r in needles if r["found"])
        distractor_correct = sum(1 for r in distractors if r["found"])
        print("{}: {}/{} needles found, {}/{} distractors handled".format(
            setting["name"], needle_found, len(needles),
            distractor_correct, len(distractors)))

    dollar = chr(36)
    print()
    print("Total cost: {}{:.4f}".format(dollar, total_cost))

    outdir = PROJECT_ROOT / "logs" / "needle_haystack"
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = outdir / "{}_needle_results.json".format(ts)
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump({"results": all_results, "cost": total_cost}, f, indent=2, default=str)
    print("Results: {}".format(outfile))


if __name__ == "__main__":
    run_experiment()
