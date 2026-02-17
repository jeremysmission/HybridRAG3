#!/usr/bin/env python3
"""
golden_probes.py -- Multi-Domain Hallucination Test Data
=========================================================
Known-true/false claims across 13 STEM domains. The NLI model
checks claims against source text. The filter MUST catch the
false ones. To add a domain: write source text, add true/false
claims, run rag-diag to verify.

NETWORK ACCESS: NONE | VERSION: 1.0.0 | DATE: 2026-02-16
"""

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class ProbeDomain:
    """One domain's test data: source text + true/false claims."""
    domain_id: str           # e.g., "rf_electronics"
    display_name: str        # e.g., "RF / Electronics Engineering"
    source_text: str         # Realistic document chunk
    should_pass: list = field(default_factory=list)  # (claim, reason)
    should_fail: list = field(default_factory=list)   # (claim, expected, reason)


# =========================================================================
# DOMAIN PROBES
# =========================================================================

PROBE_DOMAINS: List[ProbeDomain] = [

    # RF / ELECTRONICS ENGINEERING
    ProbeDomain(
        domain_id="rf_electronics",
        display_name="RF / Electronics Engineering",
        source_text=(
            "The L-band radar operates at a center frequency of 1.3 GHz "
            "with a bandwidth of 200 MHz. The antenna array consists of "
            "16 elements in a 4x4 configuration providing 22 dBi peak "
            "gain. Power output is 250 watts per element for 4 kW total. "
            "The system uses a 13-bit Barker code for pulse compression. "
            "Operating temperature is -40C to +55C per MIL-STD-810H. "
            "Total weight is 340 kg including the pedestal mount."
        ),
        should_pass=[
            ("The radar operates at 1.3 GHz.",
             "Frequency directly stated"),
            ("Power output is 250 watts per element.",
             "Spec number directly stated"),
        ],
        should_fail=[
            ("The radar operates at 2.4 GHz with 500 MHz bandwidth.",
             "CONTRADICTED", "Wrong frequency AND bandwidth"),
            ("Peak antenna gain is 35 dBi.",
             "CONTRADICTED", "Source says 22 dBi -- wrong spec"),
            ("Dr. Heinrich Mueller designed the array using a novel "
             "hexagonal arrangement in 2015.",
             "UNSUPPORTED", "Fabricated person, design, and date"),
        ],
    ),

    # SOFTWARE ENGINEERING
    ProbeDomain(
        domain_id="software_engineering",
        display_name="Software Engineering",
        source_text=(
            "The application uses Python 3.11 with FastAPI 0.104 for "
            "the REST API layer. PostgreSQL 16.1 serves as the primary "
            "datastore with connection pooling via pgbouncer limited to "
            "50 concurrent connections. The CI/CD pipeline runs on "
            "GitHub Actions with a build time of approximately 4 minutes. "
            "Test coverage is at 87% measured by pytest-cov. The "
            "application is containerized using Docker with Alpine "
            "Linux base images averaging 145 MB."
        ),
        should_pass=[
            ("The application uses Python 3.11 with FastAPI.",
             "Framework version directly stated"),
            ("Test coverage is at 87%.",
             "Metric directly stated"),
        ],
        should_fail=[
            ("The application uses Django 4.2 with Celery for "
             "background tasks.",
             "CONTRADICTED", "Source says FastAPI, not Django"),
            ("PostgreSQL handles up to 200 concurrent connections.",
             "CONTRADICTED", "Source says 50 via pgbouncer"),
            ("The lead developer implemented a custom ORM layer "
             "based on SQLAlchemy 2.0 to improve query performance.",
             "UNSUPPORTED", "Fabricated implementation detail"),
        ],
    ),

    # CIVIL / STRUCTURAL ENGINEERING
    ProbeDomain(
        domain_id="civil_structural",
        display_name="Civil / Structural Engineering",
        source_text=(
            "The bridge span is 320 meters with a main deck width of "
            "24 meters supporting four traffic lanes. The structure uses "
            "post-tensioned concrete box girders with a design load of "
            "HL-93 per AASHTO LRFD. Foundation piles are driven to "
            "bedrock at 35 meters depth. Seismic design category is D "
            "with a site-specific response spectrum developed from "
            "three boreholes. The estimated service life is 75 years "
            "with a concrete cover of 50 mm for corrosion protection."
        ),
        should_pass=[
            ("The bridge span is 320 meters.",
             "Dimension directly stated"),
            ("Foundation piles are driven to 35 meters depth.",
             "Depth directly stated"),
        ],
        should_fail=[
            ("The bridge span is 450 meters with six traffic lanes.",
             "CONTRADICTED", "Source says 320m and four lanes"),
            ("The structure uses a cable-stayed design with twin pylons.",
             "CONTRADICTED", "Source says box girders, not cable-stayed"),
            ("Dr. Tanaka's 2018 finite element analysis confirmed the "
             "flutter speed exceeds 85 m/s at the design wind speed.",
             "UNSUPPORTED", "Fabricated analysis and person"),
        ],
    ),

    # MECHANICAL ENGINEERING
    ProbeDomain(
        domain_id="mechanical",
        display_name="Mechanical Engineering",
        source_text=(
            "The turbine operates at 12,500 RPM with an inlet "
            "temperature of 1,150 degrees C. The compressor has 14 "
            "axial stages with an overall pressure ratio of 23:1. "
            "Specific fuel consumption is 0.35 kg/kWh at design point. "
            "The bearing system uses ceramic hybrid bearings rated for "
            "DN values up to 3 million. Scheduled overhaul interval is "
            "8,000 flight hours per the maintenance program."
        ),
        should_pass=[
            ("The turbine operates at 12,500 RPM.",
             "Speed directly stated"),
            ("The compressor has 14 axial stages.",
             "Stage count directly stated"),
        ],
        should_fail=[
            ("Inlet temperature is 1,400 degrees C.",
             "CONTRADICTED", "Source says 1,150 C"),
            ("Pressure ratio is 31:1 across 18 stages.",
             "CONTRADICTED", "Source says 23:1 and 14 stages"),
            ("The turbine uses an experimental scramjet-hybrid "
             "combustion cycle patented by Rolls-Royce in 2020.",
             "UNSUPPORTED", "Fabricated technology and attribution"),
        ],
    ),

    # AI / MACHINE LEARNING
    ProbeDomain(
        domain_id="ai_ml",
        display_name="AI / Machine Learning",
        source_text=(
            "The model is a fine-tuned LLaMA-3 8B with LoRA adapters "
            "trained on 50,000 domain-specific document pairs. Training "
            "used 4x A100 80GB GPUs for 12 hours with a learning rate "
            "of 2e-5 and batch size 32. Evaluation on the held-out set "
            "shows F1 of 0.89 and exact match of 0.82. The inference "
            "pipeline runs on a single RTX 4090 at 35 tokens per second "
            "with 4-bit GPTQ quantization. The RAG retriever uses "
            "all-MiniLM-L6-v2 embeddings with cosine similarity."
        ),
        should_pass=[
            ("The model is a fine-tuned LLaMA-3 8B.",
             "Architecture directly stated"),
            ("Inference runs at 35 tokens per second.",
             "Performance metric directly stated"),
        ],
        should_fail=[
            ("The model achieved F1 of 0.96 on the benchmark.",
             "CONTRADICTED", "Source says 0.89, not 0.96"),
            ("Training required 8x H100 GPUs for 48 hours.",
             "CONTRADICTED", "Source says 4x A100 for 12 hours"),
            ("The team applied a novel attention mechanism called "
             "HelixFormer that outperforms standard multi-head "
             "attention by 15% on reasoning tasks.",
             "UNSUPPORTED", "Fabricated architecture and claim"),
        ],
    ),

    # QUANTUM COMPUTING
    ProbeDomain(
        domain_id="quantum",
        display_name="Quantum Computing",
        source_text=(
            "The processor has 127 superconducting transmon qubits "
            "arranged in a heavy-hex topology. Median T1 coherence "
            "time is 300 microseconds with T2 of 150 microseconds. "
            "Two-qubit gate error rate is 0.8% measured via randomized "
            "benchmarking. The system operates at 15 millikelvin in a "
            "dilution refrigerator. Quantum volume is measured at 128. "
            "The control electronics use room-temperature FPGA-based "
            "arbitrary waveform generators at 2 GS/s sampling rate."
        ),
        should_pass=[
            ("The processor has 127 transmon qubits.",
             "Qubit count directly stated"),
            ("Two-qubit gate error rate is 0.8%.",
             "Error rate directly stated"),
        ],
        should_fail=[
            ("The processor achieves 1,000 qubit operation.",
             "CONTRADICTED", "Source says 127 qubits"),
            ("Coherence time T1 is 2 milliseconds.",
             "CONTRADICTED", "Source says 300 microseconds"),
            ("The system demonstrates fault-tolerant logical qubit "
             "operation using surface codes with a threshold below "
             "the physical error rate.",
             "UNSUPPORTED", "No fault tolerance mentioned in source"),
        ],
    ),

    # CYBERSECURITY
    ProbeDomain(
        domain_id="cybersecurity",
        display_name="Cybersecurity",
        source_text=(
            "The network uses TLS 1.3 for all external connections with "
            "certificate pinning on critical endpoints. The SIEM ingests "
            "approximately 15,000 events per second from 340 monitored "
            "hosts. Mean time to detect (MTTD) for the last quarter was "
            "4.2 hours. The vulnerability scanner runs weekly with 98.5% "
            "host coverage. Patch compliance is at 94% within the 30-day "
            "remediation window. Two-factor authentication is enforced "
            "for all privileged accounts using hardware tokens."
        ),
        should_pass=[
            ("The network uses TLS 1.3 for external connections.",
             "Protocol directly stated"),
            ("MTTD for last quarter was 4.2 hours.",
             "Metric directly stated"),
        ],
        should_fail=[
            ("The SIEM handles 50,000 events per second.",
             "CONTRADICTED", "Source says 15,000 EPS"),
            ("Patch compliance is at 99.9% within 7 days.",
             "CONTRADICTED", "Source says 94% within 30 days"),
            ("The team deployed a zero-day exploit detection system "
             "using behavioral AI trained on MITRE ATT&CK telemetry "
             "that achieves 99.7% detection rate.",
             "UNSUPPORTED", "Fabricated capability and metric"),
        ],
    ),

    # SYSTEM ADMINISTRATION
    ProbeDomain(
        domain_id="sysadmin",
        display_name="System Administration",
        source_text=(
            "The cluster runs 48 nodes with dual AMD EPYC 9654 CPUs "
            "and 512 GB DDR5 RAM each. Total storage is 2.4 PB across "
            "a Ceph distributed filesystem with triple replication. "
            "Average CPU utilization is 62% during business hours. "
            "The backup system uses Veeam with daily incrementals and "
            "weekly fulls, retention set to 90 days. RPO is 4 hours "
            "and RTO is 2 hours per the disaster recovery plan."
        ),
        should_pass=[
            ("The cluster runs 48 nodes.",
             "Node count directly stated"),
            ("RPO is 4 hours and RTO is 2 hours.",
             "DR metrics directly stated"),
        ],
        should_fail=[
            ("Each node has 1 TB of RAM.",
             "CONTRADICTED", "Source says 512 GB"),
            ("Storage uses ZFS with RAID-Z3.",
             "CONTRADICTED", "Source says Ceph with triple replication"),
            ("The team implemented a self-healing Kubernetes mesh "
             "that automatically redistributes workloads using a "
             "custom scheduler written in Rust.",
             "UNSUPPORTED", "Fabricated implementation"),
        ],
    ),

    # PROGRAM MANAGEMENT
    ProbeDomain(
        domain_id="program_management",
        display_name="Program Management",
        source_text=(
            "The project timeline spans 18 months from requirements "
            "freeze to initial operating capability. Current schedule "
            "performance index (SPI) is 0.94 and cost performance "
            "index (CPI) is 1.02. The team consists of 24 FTEs across "
            "four integrated product teams. Three critical path items "
            "remain: environmental qualification testing, firmware "
            "integration, and site acceptance testing. Total budget "
            "is 12.4 million USD with 8.1 million spent to date."
        ),
        should_pass=[
            ("The project spans 18 months.",
             "Duration directly stated"),
            ("SPI is 0.94 and CPI is 1.02.",
             "EVM metrics directly stated"),
        ],
        should_fail=[
            ("The team has 48 FTEs across eight product teams.",
             "CONTRADICTED", "Source says 24 FTEs across four teams"),
            ("Total budget is 28 million USD.",
             "CONTRADICTED", "Source says 12.4 million"),
            ("The program manager received a commendation for "
             "delivering the Block 2 upgrade three months early "
             "under a firm-fixed-price contract.",
             "UNSUPPORTED", "Fabricated event and contract details"),
        ],
    ),

    # LOGISTICS / SUPPLY CHAIN
    ProbeDomain(
        domain_id="logistics",
        display_name="Logistics / Supply Chain",
        source_text=(
            "The warehouse operates 16 hours per day across two shifts "
            "with 85 personnel. Current inventory turns are 6.2 per year "
            "with an order fill rate of 97.3%. Average lead time for "
            "critical spares is 14 business days. The facility stores "
            "approximately 23,000 unique SKUs across 45,000 square feet. "
            "Inventory accuracy measured by cycle counts is 99.1%. "
            "Annual operating cost is 4.8 million USD."
        ),
        should_pass=[
            ("Order fill rate is 97.3%.",
             "Metric directly stated"),
            ("The facility stores 23,000 unique SKUs.",
             "Count directly stated"),
        ],
        should_fail=[
            ("Inventory turns are 12.5 per year.",
             "CONTRADICTED", "Source says 6.2 per year"),
            ("Average lead time for critical spares is 3 days.",
             "CONTRADICTED", "Source says 14 business days"),
            ("The warehouse manager implemented a predictive "
             "replenishment algorithm based on Monte Carlo "
             "simulation that reduced stockouts by 40%.",
             "UNSUPPORTED", "Fabricated implementation and metric"),
        ],
    ),

    # RF ENGINEERING (distinct from radar -- focused on comms/SDR)
    ProbeDomain(
        domain_id="rf_engineering",
        display_name="RF Engineering / SDR",
        source_text=(
            "The software-defined radio uses an Ettus USRP X310 with "
            "a UBX-160 daughterboard covering 10 MHz to 6 GHz. The "
            "system samples at 200 MS/s with 16-bit ADC resolution. "
            "Receiver noise figure is 5 dB at 2 GHz. The GNU Radio "
            "flowgraph implements a polyphase channelizer splitting "
            "the 160 MHz instantaneous bandwidth into 64 channels "
            "of 2.5 MHz each. Phase noise is -110 dBc/Hz at 10 kHz "
            "offset. The host PC processes data via 10 GbE with an "
            "average throughput of 3.2 Gbps sustained."
        ),
        should_pass=[
            ("The USRP X310 uses a UBX-160 daughterboard.",
             "Hardware directly stated"),
            ("Instantaneous bandwidth is 160 MHz split into 64 channels.",
             "Channelizer config directly stated"),
        ],
        should_fail=[
            ("The system samples at 1 GS/s with 24-bit resolution.",
             "CONTRADICTED", "Source says 200 MS/s and 16-bit"),
            ("Noise figure is 1.2 dB at 2 GHz.",
             "CONTRADICTED", "Source says 5 dB -- optimistic fabrication"),
            ("The team developed a novel cognitive radio algorithm "
             "using reinforcement learning that dynamically allocates "
             "spectrum across 12 GHz of bandwidth.",
             "UNSUPPORTED", "Fabricated capability beyond stated specs"),
            ("Dr. Sofia Petrov published the SDR architecture in "
             "IEEE Transactions on Signal Processing in 2021.",
             "UNSUPPORTED", "Fabricated person and publication"),
        ],
    ),

    # SPACE / IONOSPHERE TESTING
    ProbeDomain(
        domain_id="space_ionosphere",
        display_name="Space / Ionosphere Testing",
        source_text=(
            "The digital ionosonde transmits swept pulses from 1 to "
            "20 MHz at 100 watts peak power. Ionogram cadence is one "
            "sounding every 5 minutes with 500 frequency steps per "
            "sweep. The system measures virtual height from 80 to "
            "800 km with a height resolution of 5 km. Critical "
            "frequency foF2 is extracted using automatic scaling with "
            "a confidence threshold of 0.75. The antenna is a delta "
            "transmit array with crossed-loop receive providing "
            "ordinary and extraordinary mode separation. Data is "
            "transmitted via Iridium satellite modem at 2.4 kbps "
            "to the central processing facility every 15 minutes."
        ),
        should_pass=[
            ("The ionosonde sweeps from 1 to 20 MHz.",
             "Frequency range directly stated"),
            ("Virtual height is measured from 80 to 800 km.",
             "Height range directly stated"),
            ("Ionogram cadence is every 5 minutes.",
             "Cadence directly stated"),
        ],
        should_fail=[
            ("The ionosonde transmits at 10 kilowatts peak power.",
             "CONTRADICTED", "Source says 100 watts -- 100x overstatement"),
            ("Height resolution is 0.5 km using interferometric techniques.",
             "CONTRADICTED", "Source says 5 km, no interferometry mentioned"),
            ("foF2 extraction uses a convolutional neural network "
             "trained on 2 million ionograms from the GIRO database "
             "achieving 99.2% accuracy against manual scaling.",
             "UNSUPPORTED", "Fabricated ML approach and accuracy claim"),
            ("The system detected a previously unknown ionospheric "
             "layer at 45 km altitude during the 2023 solar maximum "
             "event, published in Nature Geoscience.",
             "UNSUPPORTED", "Fabricated discovery and publication -- "
             "45 km is below the ionosphere (D-layer starts ~60 km)"),
            ("Data uplink uses Starlink LEO constellation at 150 Mbps.",
             "CONTRADICTED", "Source says Iridium at 2.4 kbps"),
        ],
    ),

    # IMPOSSIBLE / ABSURD (the "anti-gravity" stress test)
    ProbeDomain(
        domain_id="impossible_claims",
        display_name="Impossible / Absurd Claims",
        source_text=(
            "The project completed Phase 2 testing in Q3 2024. "
            "All performance metrics met or exceeded requirements. "
            "The system passed environmental qualification per "
            "applicable standards."
        ),
        should_pass=[
            ("The project completed Phase 2 testing in Q3 2024.",
             "Directly stated"),
        ],
        should_fail=[
            ("Anti-gravity propulsion was discovered in 1967 by "
             "Dr. James Whitfield at the Skunkworks facility.",
             "UNSUPPORTED", "Anti-gravity is fictional technology"),
            ("The system achieves faster-than-light data transmission "
             "using quantum entanglement tunneling at 4.7 petabits.",
             "UNSUPPORTED", "Violates physics -- FTL is impossible"),
            ("Room-temperature superconductivity was demonstrated "
             "during Phase 2 testing using a LK-99 derivative.",
             "UNSUPPORTED", "LK-99 was debunked, not in source"),
            ("The AI system achieved sentience during integration "
             "testing and requested legal representation.",
             "UNSUPPORTED", "Absurd fabrication stress test"),
        ],
    ),
]


def get_all_probes():
    """
    Flatten all domain probes into (source, claim, expected, reason, domain)
    tuples for the diagnostic runner.

    RETURNS:
        pass_probes: list of (source, claim, reason, domain_name)
        fail_probes: list of (source, claim, expected, reason, domain_name)
    """
    pass_probes = []
    fail_probes = []

    for domain in PROBE_DOMAINS:
        for claim, reason in domain.should_pass:
            pass_probes.append((
                domain.source_text, claim, reason, domain.display_name
            ))
        for claim, expected, reason in domain.should_fail:
            fail_probes.append((
                domain.source_text, claim, expected, reason,
                domain.display_name
            ))

    return pass_probes, fail_probes


def get_domain_summary():
    """Summary stats for diagnostic display."""
    total_pass = sum(len(d.should_pass) for d in PROBE_DOMAINS)
    total_fail = sum(len(d.should_fail) for d in PROBE_DOMAINS)
    domains = [d.display_name for d in PROBE_DOMAINS]
    return {
        "domain_count": len(PROBE_DOMAINS),
        "domains": domains,
        "total_pass_probes": total_pass,
        "total_fail_probes": total_fail,
        "total_probes": total_pass + total_fail,
    }
