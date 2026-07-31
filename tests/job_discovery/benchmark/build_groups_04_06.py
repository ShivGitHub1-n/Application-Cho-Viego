# ruff: noqa: E501

"""Build the independently authored calibration Groups 04-06 fixture slice."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "job_discovery" / "benchmark"


INHERITED_KNOWN_LEVEL_CASES = {
    11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 25, 27, 28, 30,
}

INHERITED_ARRANGEMENT_UPDATES = {
    6: (
        "The position is based in Toronto with a regular office presence",
        "The Toronto position has a hybrid schedule with regular office presence",
        "The Toronto position has a hybrid schedule with regular office presence.",
        "hybrid",
    ),
    11: (
        "The Vancouver office is open three days each week.",
        "The Vancouver office uses a hybrid schedule with three office days each week.",
        "The Vancouver office uses a hybrid schedule with three office days each week.",
        "hybrid",
    ),
    16: (
        "The position is in Ottawa with a regular office schedule.",
        "The hybrid position is based in Ottawa with regular office attendance.",
        "The hybrid position is based in Ottawa with regular office attendance.",
        "hybrid",
    ),
    25: (
        "The role is based in Kitchener with regular lab days.",
        "The hybrid role is based in Kitchener with regular lab days.",
        "The hybrid role is based in Kitchener with regular lab days.",
        "hybrid",
    ),
    30: (
        "The Toronto laboratory combines on-site collaboration with Canadian authorization requirements and offers no sponsorship.",
        "The Toronto laboratory supports a remote arrangement with Canadian authorization requirements and offers no sponsorship.",
        "The Toronto laboratory uses a remote arrangement in Toronto.",
        "remote",
    ),
}


def _repair_inherited_metadata(cases: list[dict[str, object]]) -> list[dict[str, object]]:
    for case in cases:
        number = int(str(case["case_id"])[-3:])
        posting = case["posting"]
        company = posting["company"]
        if number in INHERITED_ARRANGEMENT_UPDATES:
            old_text, source_text, location_text, arrangement = INHERITED_ARRANGEMENT_UPDATES[number]
            posting["description"] = posting["description"].replace(old_text, source_text, 1)
            if number == 6:
                posting["description"] = posting["description"].replace(
                    "regular office presence. and requires Canadian work authorization",
                    "regular office presence and requires Canadian work authorization",
                    1,
                )
            posting["work_arrangement"] = arrangement
            location_fact = next(fact for fact in posting["posting_facts"] if fact["kind"] == "location")
            location_fact["statement"] = location_text

        posted_date = posting["posted_date"]
        if posted_date is not None:
            if number in INHERITED_KNOWN_LEVEL_CASES:
                authority_sentence = (
                    f"{company} published this full-time opening on {posted_date} "
                    f"and describes it as a {posting['posting_level']}-level role."
                )
            else:
                authority_sentence = f"{company} published the full-time opening on {posted_date}."
        else:
            if posting["posting_level"] == "unknown":
                authority_sentence = f"{company} describes this as a full-time position; the role level is unstated."
            else:
                authority_sentence = f"{company} describes this as a full-time position."
        if authority_sentence not in posting["description"]:
            posting["description"] = posting["description"].rstrip() + " " + authority_sentence

        facts = posting["posting_facts"]
        if posted_date is not None and not any(fact["kind"] == "posting_date" for fact in facts):
            facts.append({
                "fact_id": f"posting:{case['case_id']}:posting_date:posting-date",
                "kind": "posting_date",
                "statement": f"{company} published the opening on {posted_date}.",
            })
        if not any(fact["kind"] == "employment_type" for fact in facts):
            facts.append({
                "fact_id": f"posting:{case['case_id']}:employment_type:employment-type",
                "kind": "employment_type",
                "statement": "The position is full-time employment.",
            })
    return cases


PROFILES = {
    "cal-profile-04": {
        "summary": "Robotics software engineer who integrated a warehouse rover's localization, sensors, and field diagnostics across outdoor trials.",
        "skills": ["C++", "Python", "ROS 2", "Linux", "robot localization", "sensor integration", "simulation", "pytest"],
        "experience_years": 3.5,
        "education_summary": "Bachelor of Applied Science in Mechatronics Engineering",
        "items": [
            ("e1", "demonstrated", "Maintained C++ ROS 2 nodes for a warehouse rover's localization and route-planning pipeline.", ["robotics software", "localization", "planning integration"], ["C++", "ROS 2"]),
            ("e2", "demonstrated", "Calibrated lidar and wheel-odometry sensors by checking coordinate frames against measured fixture positions.", ["sensor integration", "coordinate frames", "calibration"], ["Python", "ROS 2"]),
            ("e3", "demonstrated", "Integrated a camera perception package into the navigation stack without owning model training or dataset development.", ["perception integration", "software integration"], ["Python", "Linux"]),
            ("e4", "demonstrated", "Used Linux logs and field replay tools to isolate stale pose updates during supervised outdoor runs.", ["field debugging", "logging", "operational verification"], ["Linux", "Python"]),
            ("e5", "demonstrated", "Automated simulation checks and safety sign-off scenarios for obstacle stops before rover release trials.", ["simulation", "test automation", "safety verification"], ["Python", "pytest"]),
            ("e6", "reviewed_skill", "Reviewed CUDA terminology and neural-network deployment notes without shipping a GPU or trained model.", ["CUDA"], ["CUDA"]),
            ("e7", "coursework", "Completed a controls laboratory with a simulated differential-drive robot and synthetic sensor streams.", ["controls coursework"], ["MATLAB", "simulation"]),
        ],
    },
    "cal-profile-05": {
        "summary": "Firmware engineer who shipped low-power logger software with bus diagnostics, real-time scheduling, and hardware-in-loop release checks.",
        "skills": ["C", "C++", "microcontrollers", "FreeRTOS", "I2C", "SPI", "UART", "CAN", "hardware-in-loop", "Git"],
        "experience_years": 4.0,
        "education_summary": "Bachelor of Engineering in Computer Engineering",
        "items": [
            ("e1", "demonstrated", "Wrote C firmware drivers for I2C humidity and SPI flash devices on an STM32-based environmental logger.", ["firmware", "peripheral drivers", "memory devices"], ["C", "I2C", "SPI", "STM32"]),
            ("e2", "demonstrated", "Tuned FreeRTOS task periods and stack budgets while preserving wake timing under low-battery conditions.", ["RTOS", "timing constraints", "memory constraints"], ["C", "FreeRTOS"]),
            ("e3", "demonstrated", "Brought up prototype boards with UART and CAN diagnostics, using an oscilloscope and logic analyzer to trace faults.", ["board bring-up", "hardware-software debugging"], ["UART", "CAN", "oscilloscope", "logic analyzer"]),
            ("e4", "demonstrated", "Maintained a signed bootloader update path and Git release checklist for production logger firmware.", ["bootloaders", "release practices", "version control"], ["C", "Git"]),
            ("e5", "demonstrated", "Extended unit, integration, and hardware-in-the-loop tests for sensor wake, sleep, and brownout recovery behavior.", ["unit testing", "integration testing", "hardware-in-loop testing"], ["C", "Python"]),
            ("e6", "reviewed_skill", "Studied Zephyr scheduling examples but did not own a shipped Zephyr product or RTOS migration.", ["Zephyr"], ["Zephyr"]),
            ("e7", "coursework", "Built a hobby STM32 motor controller for a course laboratory without production release responsibility.", ["microcontroller coursework"], ["C", "STM32"]),
        ],
    },
    "cal-profile-06": {
        "summary": "Systems verification engineer who connected appliance sensors to release evidence through traceability, test benches, and cross-team defect reviews.",
        "skills": ["Python", "MATLAB", "requirements traceability", "hardware-in-loop", "data acquisition", "root-cause analysis", "CAN", "test automation"],
        "experience_years": 5.0,
        "education_summary": "Bachelor of Science in Systems Engineering",
        "items": [
            ("e1", "demonstrated", "Integrated temperature, current, and door sensors with actuator commands during connected-appliance system bring-up.", ["sensor integration", "actuator integration", "system bring-up"], ["CAN", "Python"]),
            ("e2", "demonstrated", "Mapped product requirements to interface-control checks and kept traceability current through release reviews.", ["requirements traceability", "interface control", "verification planning"], ["Python"]),
            ("e3", "demonstrated", "Built a Python data-acquisition bench that reproduced intermittent failures and supported root-cause analysis.", ["test-bench design", "data acquisition", "root-cause analysis"], ["Python"]),
            ("e4", "demonstrated", "Executed control-loop and hardware-in-loop tests, recording acceptance results against the verification plan.", ["control-system testing", "hardware-in-loop testing"], ["MATLAB", "Python"]),
            ("e5", "demonstrated", "Coordinated electrical, mechanical, and software engineers through fixture changes, defect triage, and release sign-off.", ["cross-functional integration", "verification leadership"], ["Python"]),
            ("e6", "reviewed_skill", "Reviewed SolidWorks drawings and PLC terminology without owning mechanical design or industrial controls commissioning.", ["CAD", "PLC"], ["SolidWorks", "PLC"]),
            ("e7", "coursework", "Completed a control-systems laboratory using MATLAB models and simulated plant disturbances.", ["controls coursework"], ["MATLAB"]),
        ],
    },
}


CASES = [
    # group, id, title, company, team, location, arrangement, level, category, grade, eligibility, provisional, tags, focus, responsibilities, critical, required, preferred, missing, context
    ("04", 31, "Robotics Software Engineer", "Aster Vale Robotics", "Autonomy Runtime", "Toronto, Ontario, Canada", "hybrid", "mid", "robotics", "excellent", "eligible", False, ["direct_robotics", "boundary"], ["e1", "e2", "e4"], [
        ("ros-runtime", "Maintain C++ ROS 2 nodes that publish synchronized pose and route-plan updates for warehouse robots."),
        ("sensor-health", "Integrate lidar and wheel-odometry health checks into the navigation runtime and incident logs."),
        ("field-release", "Run Linux replay sessions and supervised floor trials before each autonomy software release."),
    ], [("cpp-ros2", "C++ ROS 2 production ownership is critical for this autonomy runtime.", ["e1"])], [("linux-logging", "Linux logging and field-debugging experience is required for release support.", ["e4"]), ("sensor-integration", "Hands-on sensor integration is required for the navigation stack.", ["e2"])], [("simulation", "Simulation-based safety checks are preferred for release qualification.", ["e5"]), ("python", "Python tooling experience is preferred for diagnostics.", ["e4"])], [], "The Toronto team is adding runtime ownership to a mixed indoor fleet, with weekly floor trials and a small on-call rotation."),
    ("04", 32, "Autonomous Systems Integration Engineer", "Copper Finch Mobility", "Vehicle Integration Lab", "Waterloo, Ontario, Canada", "onsite", "mid", "autonomous_systems", "excellent", "eligible", False, ["autonomous_integration", "boundary"], ["e1", "e2", "e5"], [
        ("stack-integration", "Connect localization, perception, and motion-planning packages at the vehicle integration boundary."),
        ("calibration-runs", "Coordinate sensor calibration runs and record frame-transform results for the integration team."),
        ("simulation-gates", "Use simulation runs to exercise stop behavior before closed-course demonstrations."),
    ], [("stack-integration", "Autonomy-stack integration across ROS 2 packages is critical to this role.", ["e1", "e3"])], [("calibration", "Sensor calibration and frame-transform checks are required during vehicle bring-up.", ["e2"]), ("safety-tests", "Safety test execution is required before closed-course runs.", ["e5"])], [("c++", "C++ maintenance in a robotics codebase is preferred.", ["e1"]), ("linux", "Linux deployment familiarity is preferred.", ["e4"])], [], "Copper Finch operates a vehicle lab beside its Waterloo assembly floor, where integration engineers rotate through hardware and simulation stations."),
    ("04", 33, "Localization and Mapping Engineer", "Northstar Cartography", "Map Quality Group", "Montreal, Quebec, Canada", "hybrid", "senior", "autonomous_systems", "excellent", "eligible", False, ["localization_mapping", "boundary"], ["e1", "e2", "e4"], [
        ("mapping-pipeline", "Own localization and mapping components that turn lidar and wheel observations into repeatable warehouse maps."),
        ("frame-calibration", "Diagnose coordinate-frame drift and update calibration procedures with the field operations team."),
        ("replay-analysis", "Review Linux bag replays and publish map-quality findings for the next navigation build."),
    ], [("localization-mapping", "Production localization and mapping ownership is critical for this map-quality team.", ["e1"])], [("frame-calibration", "Coordinate-frame calibration is required for reliable map alignment.", ["e2"]), ("field-debugging", "Field replay and debugging practice is required for map regressions.", ["e4"])], [("python-tools", "Python analysis tooling is preferred for map-quality reports.", ["e2"]), ("safety", "Operational safety verification is preferred.", ["e5"])], [], "Northstar Cartography maintains a growing indoor-map fleet and gives the senior engineer ownership of map regressions from intake through release."),
    ("04", 34, "Perception Integration Engineer", "Lumen Orchard Automation", "Perception Interfaces", "Vancouver, British Columbia, Canada", "hybrid", "mid", "computer_vision", "good", "eligible", False, ["perception_integration", "boundary", "required_noncritical_gap"], ["e3", "e2", "e4"], [
        ("perception-interfaces", "Integrate camera perception outputs with the ROS 2 localization and planning interfaces."),
        ("sensor-checks", "Validate timestamp, frame, and sensor-health assumptions during perception handoff tests."),
        ("deployment-debugging", "Investigate Linux logs from field runs and document reproducible interface failures."),
    ], [("perception-integration", "Perception interface integration is critical; this role does not own model training.", ["e3"])], [("ros2-interfaces", "ROS 2 package integration is required for the handoff layer.", ["e1", "e3"]), ("field-logs", "Field log analysis is required for deployment debugging.", ["e4"]), ("runtime-performance", "Production ownership of perception-runtime latency investigation during on-robot deployments is required.", ["e3", "e4"])], [("computer-vision", "Computer-vision package familiarity is preferred.", ["e3"]), ("simulation", "Simulation coverage is preferred.", ["e5"])], [], "Lumen Orchard's Vancouver team ships perception interfaces to a partner autonomy group; model training remains with a separate research unit."),
    ("04", 35, "Senior Data Platform Engineer", "Harbor Metric Cooperative", "Operations Data Platform", "Toronto, Ontario, Canada", "remote", "senior", "data_engineering", "dont_match", "eligible", False, ["keyword_trap", "non_robotics_responsibilities"], ["e4"], [
        ("warehouse-models", "Design SQL warehouse models for billing, retention, and finance reporting."),
        ("batch-orchestration", "Operate scheduled data pipelines and resolve late-arriving source records."),
        ("stakeholder-analytics", "Translate product questions into dashboards and quarterly metric definitions."),
    ], [("sql-platform", "SQL warehouse ownership is critical for this data platform position.", [])], [("pipeline-operations", "Production batch-pipeline operations are required.", [])], [("robotics-data", "Robotics telemetry experience is preferred but is not part of the core duties.", ["e4"])], ["sql-platform", "pipeline-operations"], "Harbor Metric builds financial reporting products; its platform squad owns warehouse reliability rather than robots, vehicles, or physical autonomy systems."),
    ("04", 36, "Controls and Mechatronics Engineer", "Redwood Motion Works", "Actuator Qualification", "Austin, Texas, United States", "onsite", "mid", "controls", "dont_match", "ineligible", False, ["authorization_conflict", "controls_adjacency"], ["e5", "e7"], [
        ("actuator-tuning", "Tune servo gains and validate motor-current limits on production actuator assemblies."),
        ("bench-instrumentation", "Build electrical test fixtures and interpret oscilloscope traces during actuator qualification."),
        ("design-reviews", "Approve wiring, connector, and enclosure changes with the electrical design group."),
    ], [("simulation-safety", "Simulation-based safety verification is the critical technical qualification for this actuator laboratory.", ["e5"])], [("controls-validation", "Production controls validation is required for actuator release.", [])], [("robotics", "Robotics software exposure is preferred for test automation.", ["e5"])], ["controls-validation"], "Redwood Motion Works requires an employee authorized to work in the United States without sponsorship at its Austin laboratory."),
    ("04", 37, "Staff Simulation Engineer", "Morrow Field Systems", "Simulation Infrastructure", "Calgary, Alberta, Canada", "hybrid", "staff", "robotics", "dont_match", "ineligible", False, ["level_mismatch", "simulation_tooling"], ["e5", "e4"], [
        ("sim-platform", "Set the technical direction for a multi-team robotics simulation platform and its test libraries."),
        ("staff-influence", "Lead architecture reviews, mentor engineers, and establish simulation standards across product groups."),
        ("release-governance", "Own the simulation release calendar and sign off on risk controls for customer demonstrations."),
    ], [("staff-authority", "Staff-level organizational leadership and architecture ownership are critical to this position.", [])], [("simulation", "Robotics simulation delivery is required for the platform roadmap.", ["e5"])], [("linux", "Linux tooling is preferred.", ["e4"])], ["staff-authority"], "Morrow Field Systems expects staff-level influence across several product groups, including architecture governance and people mentoring beyond an individual contributor remit."),
    ("04", 38, "Field Robotics Reliability Engineer", "Saffron Peak Logistics", "Fleet Reliability", "Ottawa, Ontario, Canada", "hybrid", "senior", "robotics", "excellent", "eligible", False, ["field_debugging", "safety_verification"], ["e4", "e5", "e2"], [
        ("fleet-debugging", "Investigate pose, sensor, and navigation faults reported by operators during supervised fleet runs."),
        ("log-pipelines", "Improve Linux log collection and replay scripts so field incidents reach developers with usable context."),
        ("safety-release", "Partner with safety staff on stop-behavior checks and operational readiness reviews."),
    ], [("field-operations", "Field robotics debugging and operational verification are critical responsibilities.", ["e4", "e5"])], [("linux-logging", "Linux logging and incident analysis are required.", ["e4"]), ("safety", "Safety-release verification is required.", ["e5"])], [("ros2", "ROS 2 development is preferred.", ["e1"]), ("mapping", "Localization familiarity is preferred.", ["e2"])], [], "Saffron Peak supports autonomous delivery pilots across Ottawa and uses a rotating field schedule tied to operator reports and safety gates."),
    ("04", 39, "Director of Autonomous Systems", "Cedar Relay Technologies", "Autonomy Architecture", "Toronto, Ontario, Canada", "hybrid", "lead", "autonomous_systems", "dont_match", "ineligible", False, ["level_mismatch", "staff_scope_conflict"], ["e1", "e4"], [
        ("portfolio-architecture", "Set an autonomy architecture across multiple product lines and negotiate interfaces with executive stakeholders."),
        ("organization-building", "Build the engineering organization, hire managers, and own annual staffing and delivery plans."),
        ("customer-strategy", "Represent the autonomy portfolio in customer roadmaps and contractual readiness reviews."),
    ], [("portfolio-leadership", "Director-level portfolio and organizational leadership are critical to this position.", [])], [("executive-influence", "Executive stakeholder influence and multi-team planning are required.", [])], [("ros2", "Robotics software familiarity is preferred.", ["e1"])], ["portfolio-leadership", "executive-influence"], "Cedar Relay is hiring an executive leader for a multi-product portfolio; the role is not an individual contributor position despite its autonomy title."),
    ("04", 40, "Robotics Systems Engineer", "Juniper Arc Labs", "Mobile Systems Team", "Remote within Canada; exact city not stated", "remote", "unknown", "robotics", "weak", "unknown", True, ["incomplete_posting", "unknown_eligibility", "material_adjacency_stretch"], ["e1", "e2"], [
        ("robotics-integration", "Integrate navigation software with mobile-robot sensors and support prototype trials."),
        ("test-notes", "Record simulation and bench-test results for the next hardware revision."),
        ("support-rotation", "Participate in a small engineering support rotation for integration defects."),
        ("actuator-controls-trials", "Integrate actuator interfaces and debug production controls behavior during prototype trials."),
    ], [("robotics-software", "Robotics software integration is critical to the advertised systems work.", ["e1"])], [("sensor-testing", "Sensor testing and calibration experience are required.", ["e2"]), ("linux-debugging", "Linux field-debugging ownership is required for integration support.", ["e4"]), ("actuator-controls-integration", "Hands-on actuator-interface integration and production controls debugging during prototype trials are required.", ["e5"])], [("python", "Python test tooling is preferred.", ["e5"])], [], "Juniper Arc Labs truncated the posting before stating the level, posting date, sponsorship policy, or exact remote geography; those details require confirmation."),

    ("05", 41, "Firmware Engineer", "Granite Current Devices", "Power Logger Firmware", "Toronto, Ontario, Canada", "hybrid", "mid", "firmware", "excellent", "eligible", False, ["direct_firmware", "boundary"], ["e1", "e2", "e3", "e5"], [
        ("driver-ownership", "Own C drivers for I2C environmental sensors and SPI storage on a battery-powered logger."),
        ("rtos-scheduling", "Tune FreeRTOS scheduling, memory budgets, and wake timing across logger operating modes."),
        ("board-debugging", "Commission prototype controller boards by checking serial-console and CAN traces, then document electrical fault isolation for production handoff."),
    ], [("c-firmware", "Production C firmware and peripheral-driver ownership are critical for the logger platform.", ["e1"])], [("rtos", "RTOS scheduling under timing and memory limits is required.", ["e2"]), ("bring-up", "Board bring-up and hardware-software debugging are required.", ["e3"])], [("hil", "Hardware-in-loop testing is preferred.", ["e5"]), ("bootloader", "Bootloader release experience is preferred.", ["e4"])], [], "Granite Current builds environmental monitors for Canadian utilities, and this team owns firmware from board bring-up through field release."),
    ("05", 42, "Embedded Driver Engineer", "Blue Lantern Instruments", "Device Connectivity", "Hamilton, Ontario, Canada", "onsite", "mid", "embedded_systems", "good", "eligible", False, ["driver_board_support", "boundary", "required_noncritical_gap"], ["e1", "e3", "e5"], [
        ("bus-drivers", "Develop and maintain C drivers for SPI flash, I2C sensors, and UART service ports."),
        ("board-support", "Extend the board-support package and verify pin mappings during prototype spins."),
        ("diagnostic-tools", "Create small Python diagnostic tools for factory and lab technicians."),
    ], [("peripheral-drivers", "Peripheral-driver development is critical for the connectivity board.", ["e1"])], [("board-support", "Board-support and prototype verification are required.", ["e3"]), ("embedded-tests", "Embedded unit and integration testing are required.", ["e5"]), ("interrupt-dma-depth", "Production ownership of interrupt/DMA concurrency and high-rate peripheral fault handling is required.", ["e1", "e2"])], [("rtos", "RTOS exposure is preferred.", ["e2"]), ("can", "CAN diagnostics are preferred.", ["e3"])], [], "Blue Lantern Instruments runs a compact Hamilton hardware lab where driver engineers work beside manufacturing test and sustaining engineering."),
    ("05", 43, "Real-Time Firmware Engineer", "Elm Circuit Systems", "Timing and Control Firmware", "London, Ontario, Canada", "hybrid", "senior", "firmware", "excellent", "eligible", False, ["real_time_systems", "boundary"], ["e2", "e3", "e4"], [
        ("deadline-analysis", "Analyze task deadlines and interrupt latency for a motor-monitoring controller."),
        ("rtos-components", "Implement FreeRTOS components and review memory use on constrained microcontrollers."),
        ("fault-recovery", "Add watchdog, bootloader, and serial recovery behavior for service technicians."),
    ], [("realtime-c", "C real-time firmware ownership is critical to the controller schedule.", ["e2"])], [("timing-memory", "Timing and memory analysis on microcontrollers are required.", ["e2"]), ("recovery", "Bootloader and fault-recovery development are required.", ["e4"])], [("can", "CAN bus debugging is preferred.", ["e3"]), ("hil", "Hardware-in-loop coverage is preferred.", ["e5"])], [], "Elm Circuit's timing group maintains safety-adjacent motor monitors and measures every interrupt path on bench hardware before release."),
    ("05", 44, "Embedded Linux Platform Engineer", "Quarry Signal Labs", "Edge Device Platform", "Toronto, Ontario, Canada", "hybrid", "mid", "embedded_systems", "dont_match", "eligible", False, ["embedded_linux_adjacency", "boundary"], ["e3", "e4", "e5"], [
        ("linux-image", "Maintain the embedded Linux image and the boundary between user-space services and device firmware."),
        ("update-service", "Harden boot and update flows for field devices with intermittent connectivity."),
        ("integration-lab", "Run serial, CAN, and hardware-in-loop checks in the edge-device integration lab."),
    ], [("embedded-linux", "Embedded Linux platform ownership is critical for the edge-device image.", [])], [("device-boundary", "Hardware-software integration and release testing are required.", ["e3", "e5"]), ("boot-update", "Boot and update flow work is required.", ["e4"])], [("c-firmware", "C firmware experience is preferred.", ["e1"]), ("rtos", "RTOS familiarity is preferred.", ["e2"])], ["embedded-linux"], "Quarry Signal Labs ships rugged edge gateways; this platform team owns the Linux image while a separate group owns most MCU firmware."),
    ("05", 45, "Firmware Validation Engineer", "Pineglass Metering", "Release Verification", "Kitchener, Ontario, Canada", "onsite", "senior", "verification", "excellent", "eligible", False, ["validation_testing", "boundary"], ["e4", "e5", "e3"], [
        ("release-matrix", "Own the firmware release matrix across logger boards, bootloader versions, and sensor configurations."),
        ("hil-regression", "Expand hardware-in-loop regression for wake, sleep, brownout, and update recovery paths."),
        ("fault-reproduction", "Reproduce board failures with serial traces and lab instruments before release sign-off."),
    ], [("firmware-validation", "Firmware validation ownership is critical to the release-verification team.", ["e5", "e4"])], [("hil-testing", "Hardware-in-loop integration testing is required.", ["e5"]), ("instrumented-debugging", "Instrumented board debugging is required.", ["e3"])], [("c-drivers", "C driver knowledge is preferred.", ["e1"]), ("rtos", "RTOS timing context is preferred.", ["e2"])], [], "Pineglass Metering releases utility hardware quarterly and expects the validation engineer to block a release when a reproducible field fault remains open."),
    ("05", 46, "Electrical Hardware Design Engineer", "Westhaven Power Assemblies", "Power Electronics Design", "Burlington, Ontario, Canada", "onsite", "senior", "hardware_systems_integration", "dont_match", "eligible", False, ["hardware_design_gap", "electrical_design"], ["e3"], [
        ("schematic-design", "Own schematics and PCB layout for high-voltage power-conversion assemblies."),
        ("compliance-testing", "Lead electrical safety, EMC, and thermal compliance testing for new assemblies."),
        ("supplier-release", "Approve component substitutions and manufacturing release packages with suppliers."),
    ], [("electrical-design", "High-voltage schematic and PCB design ownership is critical for this electrical role.", [])], [("compliance", "Electrical compliance testing and supplier release are required.", [])], [("firmware", "Firmware collaboration is preferred but is not the primary responsibility.", ["e3"])], ["electrical-design", "compliance"], "Westhaven Power Assemblies designs high-voltage conversion hardware; the position is centered on electrical design and compliance rather than firmware."),
    ("05", 47, "Product Software Engineer", "Cobalt Orchard Software", "Connected Applications", "Toronto, Ontario, Canada", "remote", "mid", "software_engineering", "dont_match", "eligible", False, ["keyword_trap", "embedded_keyword"], ["e5"], [
        ("web-services", "Build customer-facing web services and TypeScript interfaces for device account management."),
        ("cloud-observability", "Operate cloud APIs, dashboards, and alerting for connected-device usage data."),
        ("product-delivery", "Partner with product managers on feature delivery, documentation, and support rotations."),
    ], [("web-platform", "Web-service ownership is critical for this software product role.", [])], [("cloud-operations", "Cloud API delivery and operational support are required.", [])], [("embedded-devices", "Interest in embedded devices is preferred but does not define the work.", ["e5"])], ["web-platform", "cloud-operations"], "Cobalt Orchard sells connected-device management software; no firmware, board, driver, or real-time ownership sits in this application team."),
    ("05", 48, "Embedded Systems Engineer", "Mariner Access Controls", "Secure Device Firmware", "Seattle, Washington, United States", "onsite", "mid", "embedded_systems", "dont_match", "ineligible", False, ["authorization_conflict", "clearance_conflict"], ["e1", "e3"], [
        ("secure-boot", "Implement secure boot and signed firmware updates for access-control controllers."),
        ("device-drivers", "Maintain C drivers for CAN-connected locks and tamper sensors."),
        ("field-certification", "Support federal customer certification tests at the Seattle laboratory."),
    ], [], [("secure-firmware", "Secure firmware and CAN driver work are required.", ["e1", "e3"])], [("rtos", "RTOS experience is preferred.", ["e2"])], [], "Mariner Access Controls requires United States work authorization and customer clearance for engineers entering its federal test laboratory."),
    ("05", 49, "Staff Firmware Architect", "Signal North Automation", "Firmware Architecture", "Toronto, Ontario, Canada", "hybrid", "staff", "firmware", "dont_match", "ineligible", False, ["level_mismatch", "staff_scope_conflict"], ["e1", "e4"], [
        ("architecture-standards", "Set firmware architecture standards across six product lines and resolve cross-team design disputes."),
        ("organization-mentoring", "Mentor senior engineers, lead hiring panels, and establish a multi-year technical roadmap."),
        ("portfolio-risk", "Own portfolio-level firmware risk reviews with product and manufacturing executives."),
    ], [("staff-architecture", "Staff-level cross-product architecture authority is critical for this posting.", [])], [("portfolio-influence", "Cross-team architecture influence and roadmap ownership are required.", [])], [("c-drivers", "C driver experience is preferred.", ["e1"])], ["staff-architecture", "portfolio-influence"], "Signal North is recruiting a staff architect to govern several firmware organizations, not an engineer focused on one board or release train."),
    ("05", 50, "Embedded Test Engineer", "Maple Tide Sensors", "Device Quality", "Remote within Canada; city and sponsorship policy not stated", "remote", "unknown", "testing", "weak", "unknown", True, ["incomplete_posting", "unknown_eligibility"], ["e5", "e3"], [
        ("device-regression", "Create regression checks for sensor devices and summarize failures for firmware developers."),
        ("lab-reproduction", "Reproduce intermittent bus faults on evaluation boards when laboratory access is available."),
        ("release-notes", "Maintain test results and release notes for a small connected-device portfolio."),
    ], [("embedded-testing", "Embedded-device testing is critical to the advertised quality work.", ["e5"])], [("bus-debugging", "Bus-level debugging and reproducible test work are required.", ["e3"]), ("python-automation", "Python automation ownership across a maintained embedded test suite is required for repeatable device regression.", ["e5"])], [("python", "Python test tooling is preferred.", ["e5"])], ["python-automation"], "Maple Tide Sensors provides an incomplete posting that omits its level, exact remote geography, date, and authorization policy; those details require confirmation."),

    ("06", 51, "Systems Integration Engineer", "Ironleaf Appliance Systems", "Connected Product Integration", "Toronto, Ontario, Canada", "hybrid", "mid", "hardware_systems_integration", "excellent", "eligible", False, ["systems_integration", "boundary"], ["e1", "e2", "e3", "e5"], [
        ("sensor-actuator", "Integrate appliance sensors, actuator commands, and CAN messages during system bring-up."),
        ("interface-control", "Maintain interface-control checks and requirements traceability across electrical and software boundaries."),
        ("failure-analysis", "Use a Python data-acquisition bench to reproduce faults and document root-cause findings."),
    ], [("integration-ownership", "Sensor, actuator, and interface integration ownership is critical to this systems role.", ["e1", "e2"])], [("traceability", "Requirements traceability and test-bench execution are required.", ["e2", "e3"]), ("cross-functional", "Cross-functional release coordination is required.", ["e5"])], [("hil", "Hardware-in-loop controls testing is preferred.", ["e4"]), ("matlab", "MATLAB analysis is preferred.", ["e4"])], [], "Ironleaf Appliance Systems integrates connected kitchen products in Toronto, with systems engineers embedded in electrical, mechanical, and software release teams."),
    ("06", 52, "Verification and Test Engineer", "Blue Current Medical Devices", "Product Verification", "Mississauga, Ontario, Canada", "onsite", "senior", "verification", "good", "eligible", False, ["verification_testing", "boundary", "required_noncritical_gap"], ["e2", "e3", "e4"], [
        ("verification-plan", "Build verification plans for sensor, actuator, and communications interfaces on a regulated device."),
        ("traceability-reports", "Link requirements to test evidence and present open risks at design-control reviews."),
        ("bench-execution", "Operate data-acquisition benches and investigate failures with electrical and software partners."),
    ], [("verification-planning", "Verification planning and traceability are critical to this regulated-device role.", ["e2", "e4"])], [("test-bench", "Test-bench execution and failure investigation are required.", ["e3"]), ("cross-functional", "Electrical and software collaboration is required.", ["e5"]), ("design-control-depth", "Ownership of medical-device design-control documentation and regulated risk files is required.", ["e2", "e5"])], [("can", "CAN interface testing is preferred.", ["e1"]), ("hil", "Hardware-in-loop experience is preferred.", ["e4"])], [], "Blue Current Medical Devices runs design-control reviews for infusion equipment, and verification engineers must preserve a clear chain from requirement to result."),
    ("06", 53, "Controls Validation Engineer", "Mosaic Transit Controls", "Vehicle Controls Validation", "Ottawa, Ontario, Canada", "hybrid", "senior", "controls", "excellent", "eligible", False, ["controls_validation", "boundary"], ["e1", "e3", "e4"], [
        ("control-tests", "Validate control-loop behavior for steering and thermal actuators on a transit demonstrator."),
        ("hil-scenarios", "Design hardware-in-loop scenarios that exercise sensor dropouts, saturation, and recovery behavior."),
        ("data-analysis", "Analyze Python and MATLAB test data and publish acceptance decisions for the controls release."),
    ], [("controls-validation", "Control-system validation ownership is critical for the transit demonstrator.", ["e4"])], [("hil", "Hardware-in-loop control testing is required.", ["e4"]), ("data-tools", "Python or MATLAB test analysis is required.", ["e3", "e4"])], [("can", "CAN integration knowledge is preferred.", ["e1"]), ("requirements", "Requirements traceability is preferred.", ["e2"])], [], "Mosaic Transit Controls validates low-speed electric buses in Ottawa and expects evidence-based release decisions from the controls laboratory."),
    ("06", 54, "Hardware Bring-Up Engineer", "Copper Meadow Robotics", "Prototype Integration", "Guelph, Ontario, Canada", "onsite", "mid", "hardware_systems_integration", "excellent", "eligible", False, ["hardware_bringup", "boundary"], ["e1", "e3", "e5"], [
        ("prototype-bringup", "Bring up sensor and actuator assemblies on prototype appliance-control hardware."),
        ("interface-debugging", "Trace CAN and power-interface failures with bench instruments and captured data."),
        ("release-handoff", "Package reproducible findings for electrical, mechanical, and firmware teams before build handoff."),
    ], [("bring-up", "Prototype hardware bring-up and interface debugging are critical for this integration team.", ["e1", "e3"])], [("bench-debugging", "Bench-based data collection and root-cause analysis are required.", ["e3"]), ("cross-team", "Cross-functional handoff with electrical and firmware teams is required.", ["e5"])], [("hil", "Hardware-in-loop testing is preferred.", ["e4"]), ("requirements", "Requirements traceability is preferred.", ["e2"])], [], "Copper Meadow Robotics builds prototype inspection cells in Guelph, where bring-up engineers move between a wiring bench, test stand, and release room."),
    ("06", 55, "Manufacturing Test Engineer", "Prairie Forge Appliances", "Factory Test Engineering", "Cambridge, Ontario, Canada", "onsite", "mid", "testing", "dont_match", "eligible", False, ["manufacturing_test", "boundary"], ["e3", "e4", "e5"], [
        ("factory-fixtures", "Design manufacturing test fixtures for sensor calibration and actuator end-of-line checks."),
        ("yield-analysis", "Use Python data collection to identify yield shifts and separate fixture faults from product defects."),
        ("operator-release", "Write controlled work instructions and train operators before a station enters production."),
    ], [("manufacturing-test", "Manufacturing test ownership is critical to the factory-test engineering team.", [])], [("data-acquisition", "Data acquisition and root-cause analysis are required.", ["e3"]), ("release-controls", "Controlled validation and production release practice are required.", ["e4", "e5"])], [("can", "Industrial or CAN protocol experience is preferred.", ["e1"]), ("requirements", "Requirements traceability is preferred.", ["e2"])], ["manufacturing-test"], "Prairie Forge Appliances is moving a connected cooking line into higher volume and needs a test engineer who can turn station data into release actions."),
    ("06", 56, "Mechanical Design Engineer", "Lake Basin Structures", "Industrial Chassis Design", "Toronto, Ontario, Canada", "hybrid", "senior", "mechatronics", "dont_match", "eligible", False, ["keyword_trap", "mechanical_design_gap"], ["e5"], [
        ("cad-design", "Create detailed CAD assemblies and tolerance drawings for sheet-metal industrial enclosures."),
        ("prototype-builds", "Lead mechanical prototype builds, fit checks, and supplier drawing reviews."),
        ("thermal-structures", "Own structural and thermal design changes through manufacturing release."),
    ], [("mechanical-design", "Mechanical CAD and enclosure-design ownership are critical to this position.", [])], [("manufacturing-release", "Mechanical prototype and manufacturing release work are required.", [])], [("systems-testing", "Systems-test collaboration is preferred but does not replace mechanical design ownership.", ["e5"])], ["mechanical-design", "manufacturing-release"], "Lake Basin Structures designs industrial enclosures; the day-to-day work is mechanical design and supplier release rather than systems verification."),
    ("06", 57, "Technical Program Manager, Connected Products", "Silver Birch Software", "Platform Programs", "Toronto, Ontario, Canada", "remote", "senior", "software_engineering", "dont_match", "eligible", False, ["keyword_trap", "project_management_gap"], ["e5"], [
        ("program-roadmaps", "Own cross-team software roadmaps, delivery milestones, and executive status reviews."),
        ("vendor-coordination", "Coordinate cloud vendors, contract developers, and product launch dependencies."),
        ("risk-reporting", "Maintain program risks, budget forecasts, and decision logs for connected-product leadership."),
    ], [("program-management", "Program roadmap and delivery ownership are critical to this management position.", [])], [("executive-reporting", "Executive reporting and vendor coordination are required.", [])], [("hardware-context", "Hardware context is preferred but does not make this a verification role.", ["e5"])], ["program-management", "executive-reporting"], "Silver Birch Software runs connected-product programs from a remote platform office; this role manages delivery rather than testing hardware or controls."),
    ("06", 58, "Systems Verification Engineer", "Aurora Gate Instruments", "Regulated Systems Assurance", "Toronto, Ontario, Canada", "hybrid", "senior", "verification", "dont_match", "ineligible", False, ["license_conflict"], ["e2", "e3"], [
        ("regulated-verification", "Lead verification for safety-critical instruments and approve release evidence for customer audits."),
        ("requirements-signoff", "Interpret formal requirements and sign compliance decisions with the responsible engineer."),
        ("failure-investigation", "Coordinate root-cause investigations across electrical, mechanical, and software teams."),
    ], [("professional-license", "A Professional Engineer license is mandatory for regulated release sign-off.", [])], [("verification-signoff", "Formal verification planning and release sign-off are required.", ["e2", "e4"])], [("python", "Python test tooling is preferred.", ["e3"])], ["professional-license"], "Aurora Gate Instruments requires a current Professional Engineer license for engineers who approve its regulated customer releases."),
    ("06", 59, "Principal Controls Verification Lead", "West Coast Motion Labs", "Controls Assurance", "Toronto, Ontario, Canada", "hybrid", "lead", "controls", "dont_match", "ineligible", False, ["level_mismatch", "staff_scope_conflict"], ["e4", "e5"], [
        ("assurance-strategy", "Set controls-assurance strategy across several programs and negotiate verification commitments with customers."),
        ("team-leadership", "Lead a group of verification engineers, approve staffing plans, and coach technical leads."),
        ("executive-signoff", "Present program-level residual risk and release recommendations to executive steering committees."),
    ], [("principal-scope", "Principal-level organizational and customer-facing assurance ownership is critical.", [])], [("team-leadership", "People leadership and program-level risk ownership are required.", [])], [("hil", "Hardware-in-loop controls testing is preferred.", ["e4"])], ["principal-scope", "team-leadership"], "West Coast Motion Labs seeks a principal lead with organization-wide controls authority; the position exceeds an individual contributor validation scope."),
    ("06", 60, "Systems Test Engineer", "Willow Current Works", "Systems Test", "Remote within Canada; role level and authorization policy not stated", "remote", "unknown", "testing", "weak", "unknown", True, ["incomplete_posting", "unknown_eligibility", "material_adjacency_stretch"], ["e2", "e3"], [
        ("system-tests", "Execute system tests for sensors, actuators, and interface changes on a connected product."),
        ("trace-results", "Record test results and open reproducible defects for the next integration build."),
        ("bench-support", "Commission and calibrate physical actuator control benches, tune loops, and set up instrumentation during scheduled verification activities."),
    ], [("system-verification", "System verification work is critical to the advertised test assignment.", ["e3", "e4"])], [("test-traceability", "Test traceability and bench data collection are required.", ["e2", "e3"]), ("bench-commissioning", "Commissioning and calibration of physical actuator control benches, loop tuning, and instrumentation setup are required.", ["e3", "e4"])], [("can", "CAN or industrial-protocol testing is preferred.", ["e1"])], [], "Willow Current Works supplied a shortened advertisement that omits the level, date, authorization policy, and exact remote geography; those details require confirmation."),
]


# These are source-copy authorities.  They are deliberately keyed by case
# number only as a lookup for authored content; no wording, judgment, or
# scenario is derived from the key.
DESCRIPTION_COPY = {
31: """Aster Vale Robotics is hiring a Robotics Software Engineer for its Autonomy Runtime team in Toronto, Ontario, Canada. This hybrid, full-time mid-level role maintains C++ ROS 2 nodes that publish synchronized pose and route-plan updates for warehouse robots. You will integrate lidar and wheel-odometry health checks into the navigation runtime and its incident logs, then run Linux replay sessions and supervised floor trials before each autonomy software release. Production C++ firmware or peripheral-driver experience is not part of this position; the critical qualification is production C++ ROS 2 ownership for an autonomy runtime. Required qualifications are Linux logging and field-debugging experience plus hands-on sensor integration. Simulation-based safety checks and Python diagnostic tooling are preferred. The posting was published on 2026-07-20, and the employer confirms work authorization support for the stated location. Engineers share release notes with operations and take part in a practical floor-trial rotation.""",
32: """Copper Finch Mobility's Vehicle Integration Lab in Waterloo, Ontario, Canada, needs an Autonomous Systems Integration Engineer. This is an onsite, full-time mid-level appointment beside the vehicle assembly floor. The engineer connects localization, perception, and motion-planning packages at the vehicle integration boundary, coordinates sensor calibration runs, records frame-transform results, and uses simulation to exercise stop behavior before closed-course demonstrations. Autonomy-stack integration across ROS 2 packages is the critical qualification. Required experience includes sensor calibration and frame-transform checks and safety-test execution before closed-course runs. C++ maintenance in a robotics codebase and Linux deployment familiarity are preferred. The role was published on 2026-07-18. The employer confirms work authorization support for the stated location. Engineers rotate through hardware and simulation stations and write concise integration records for the next vehicle build. Close collaboration with perception, localization, and motion-planning owners is expected during each demonstration cycle.""",
33: """Northstar Cartography is opening a Localization and Mapping Engineer position in its Map Quality Group in Montreal, Quebec, Canada. The hybrid, full-time role is senior level and owns localization and mapping components that turn lidar and wheel observations into repeatable warehouse maps. The engineer diagnoses coordinate-frame drift, updates calibration procedures with field operations, reviews Linux bag replays, and publishes map-quality findings for the next navigation build. Production localization and mapping ownership is the critical qualification. Required qualifications are coordinate-frame calibration and field replay and debugging practice. Python analysis tooling and operational safety verification are preferred. This advertisement was published on 2026-07-19, and the employer confirms work authorization support for the stated location. Northstar gives the engineer responsibility for map regressions from intake through release. The team works with deployment technicians to reproduce drift, document the affected route, and verify the corrected map before it reaches the indoor fleet.""",
34: """Lumen Orchard Automation is seeking a Perception Integration Engineer for its Perception Interfaces team in Vancouver, British Columbia, Canada. The hybrid, full-time role is a mid-level engineering position that integrates camera perception outputs with ROS 2 localization and planning interfaces. Day-to-day work validates timestamp, frame, and sensor-health assumptions during perception handoff tests and investigates Linux logs from field runs while documenting reproducible interface failures. Perception interface integration is critical, and model training remains with a separate research unit. Required qualifications include ROS 2 package integration, field-log analysis for deployment debugging, and production ownership of perception-runtime latency investigation during on-robot deployments. Computer-vision package familiarity and simulation coverage are preferred. The posting was published on 2026-07-17. The employer confirms work authorization support for the stated location. Interface engineers attend handoffs with the autonomy group, isolate contract failures, and turn each confirmed defect into a regression check for the following release.""",
35: """Harbor Metric Cooperative is hiring a Senior Data Platform Engineer for its Operations Data Platform in Toronto, Ontario, Canada. The remote, full-time role designs SQL warehouse models for billing, retention, and finance reporting. It also operates scheduled data pipelines, resolves late-arriving source records, and translates product questions into dashboards and quarterly metric definitions. SQL warehouse ownership is critical, while production batch-pipeline operations are required. Robotics telemetry experience is preferred but does not define the work. The position is senior level, was published on 2026-07-16, and the employer confirms work authorization support for the stated location. This team works with finance and product analysts on warehouse reliability, lineage, and release notes. Applicants should be comfortable reviewing query plans, documenting source assumptions, and communicating metric changes to non-engineering partners. The job has no responsibility for robots, vehicles, sensors, autonomy software, or physical systems.""",
36: """Redwood Motion Works is recruiting a Controls and Mechatronics Engineer for its Actuator Qualification laboratory in Austin, Texas, United States. This onsite, full-time mid-level role tunes servo gains, validates motor-current limits on production actuator assemblies, builds electrical test fixtures, and interprets oscilloscope traces during qualification. Engineers approve wiring, connector, and enclosure changes with the electrical design group. Simulation-based safety verification is the critical technical qualification; production controls validation is required, and robotics software exposure is preferred for test automation. United States work authorization without sponsorship is required for this laboratory assignment. The advertisement was published on 2026-07-15. Redwood's lab works directly with electrical design and manufacturing release teams, and every actuator change receives a bench record before approval. The position emphasizes physical test execution and release evidence, with occasional software support for instrument control and repeatable qualification runs.""",
37: """Morrow Field Systems is looking for a Staff Simulation Engineer to set the technical direction for a multi-team robotics simulation platform in Calgary, Alberta, Canada. The hybrid, full-time staff role owns simulation architecture, leads architecture reviews, mentors engineers, establishes standards across product groups, and controls the simulation release calendar for customer demonstrations. Staff-level organizational leadership and architecture ownership are critical; robotics simulation delivery is required for the platform roadmap, and Linux tooling is preferred. The employer confirms work authorization support for the stated location. The advertisement was published on 2026-07-14. This position coordinates several product groups rather than maintaining one simulator in isolation. It writes platform standards, negotiates release risk, and provides technical direction when product teams disagree about scenario coverage. The role is intended for a staff-level contributor with broad influence over architecture and governance and includes regular cross-team planning responsibilities.""",
38: """Saffron Peak Logistics is adding a Field Robotics Reliability Engineer to its Fleet Reliability team in Ottawa, Ontario, Canada. This hybrid, full-time senior position investigates pose, sensor, and navigation faults reported by operators during supervised fleet runs. The engineer improves Linux log collection and replay scripts so field incidents reach developers with usable context, then partners with safety staff on stop-behavior checks and operational readiness reviews. Field robotics debugging and operational verification are critical responsibilities. Required qualifications include Linux logging and incident analysis and safety-release verification. ROS 2 development and localization familiarity are preferred. The posting was published on 2026-07-13, and the employer confirms work authorization support for the stated location. Saffron Peak supports autonomous delivery pilots with a rotating field schedule tied to operator reports and safety gates. Reliability work includes reproducing an incident, recording the operating conditions, and confirming the corrective build before a pilot resumes.""",
39: """Cedar Relay Technologies is hiring a Director of Autonomous Systems for its Autonomy Architecture organization in Toronto, Ontario, Canada. The hybrid, full-time lead role sets autonomy architecture across multiple product lines, negotiates interfaces with executive stakeholders, builds the engineering organization, hires managers, owns annual staffing and delivery plans, and represents the portfolio in customer roadmaps and contractual readiness reviews. Director-level portfolio and organizational leadership are critical. Executive stakeholder influence and multi-team planning are required, while robotics software familiarity is preferred. The employer confirms work authorization support for the stated location. The posting was published on 2026-07-12. Cedar Relay is seeking an executive leader for a multi-product portfolio, not an individual contributor focused on a single autonomy stack. The successful hire will establish governance, align product-line commitments, and make staffing and customer-readiness decisions across the organization.""",
40: """Juniper Arc Labs is seeking a Robotics Systems Engineer for its Mobile Systems Team. The available advertisement describes remote work within Canada, but the exact city is not stated. The team integrates navigation software with mobile-robot sensors, supports prototype trials, records simulation and bench-test results for hardware revisions, and participates in a small engineering support rotation for integration defects. During prototype trials, engineers integrate actuator interfaces and debug production controls behavior while preserving the conditions needed to reproduce a fault. Robotics software integration is critical. Sensor testing and calibration, Linux field debugging, and hands-on actuator-interface integration with production controls debugging are required, while Python test tooling is preferred. The posting does not state its level, posting date, sponsorship policy, or exact remote geography. Juniper says the position is full-time and expects engineers to share reproducible trial notes with hardware and navigation partners. Work includes tracing a sensor result through the integration boundary, preserving relevant bench conditions, and returning a clear defect record to the next build owner. The remaining employment and eligibility details should be confirmed with the employer.""",
41: """Granite Current Devices is hiring a Firmware Engineer for its Power Logger Firmware team in Toronto, Ontario, Canada. This hybrid, full-time mid-level role owns C drivers for I2C environmental sensors and SPI storage on a battery-powered logger. The engineer tunes FreeRTOS scheduling, memory budgets, and wake timing across logger operating modes, then commissions prototype controller boards by checking serial-console and CAN traces and documenting electrical fault isolation for production handoff. Production C firmware and peripheral-driver ownership are critical. RTOS scheduling under timing and memory limits and board bring-up with hardware-software debugging are required. Hardware-in-loop testing and bootloader release experience are preferred. The posting was published on 2026-07-11, and the employer confirms work authorization support for the stated location. Granite Current builds environmental monitors for Canadian utilities and owns firmware from board bring-up through field release. Release reviews include power-state evidence, bus diagnostics, and a traceable handoff to sustaining engineering.""",
42: """Blue Lantern Instruments is looking for an Embedded Driver Engineer in its Device Connectivity group in Hamilton, Ontario, Canada. The onsite, full-time mid-level engineer develops and maintains C drivers for SPI flash, I2C sensors, and UART service ports. The role extends the board-support package, verifies pin mappings during prototype spins, and creates small Python diagnostic tools for factory and laboratory technicians. Peripheral-driver development is critical. Board-support and prototype verification plus embedded unit and integration testing are required. The production boundary also requires ownership of interrupt/DMA concurrency and high-rate peripheral fault handling. RTOS exposure and CAN diagnostics are preferred. Blue Lantern confirms work authorization support for the stated location; the advertisement was published on 2026-07-10. The connectivity group works beside manufacturing test and sustaining engineering, so a driver change must be demonstrated on the intended board revision and documented for technicians. Success is measured by reliable peripheral behavior, useful diagnostics, and a clean handoff into the next prototype build.""",
43: """Elm Circuit Systems needs a Real-Time Firmware Engineer for its Timing and Control Firmware team in London, Ontario, Canada. This hybrid, full-time senior role analyzes task deadlines and interrupt latency for a motor-monitoring controller. It implements FreeRTOS components, reviews memory use on constrained microcontrollers, and adds watchdog, bootloader, and serial-recovery behavior for service technicians. C real-time firmware ownership is critical. Timing and memory analysis on microcontrollers and bootloader and fault-recovery development are required. CAN-bus debugging and hardware-in-loop coverage are preferred. The employer confirms work authorization support for the stated location, and the job was published on 2026-07-09. Elm Circuit measures every interrupt path on bench hardware before release and expects engineers to explain timing decisions in review records. The work spans implementation, instrumented diagnosis, recovery behavior, and controlled release of safety-adjacent motor monitors.""",
44: """Quarry Signal Labs is hiring an Embedded Linux Platform Engineer for its Edge Device Platform in Toronto, Ontario, Canada. This hybrid, full-time mid-level role maintains an embedded Linux image and the boundary between user-space services and device firmware. It hardens boot and update flows for field devices with intermittent connectivity and runs serial, CAN, and hardware-in-loop checks in the edge-device integration lab. Embedded Linux platform ownership is critical. Hardware-software integration and release testing and boot and update flow work are required. C firmware experience and RTOS familiarity are preferred. The employer confirms work authorization support for the stated location; the posting was published on 2026-07-08. Quarry Signal ships rugged edge gateways, and this team owns the Linux image while a separate group owns most MCU firmware. Work includes image maintenance, update failure reproduction, and release evidence across the device boundary.""",
45: """Pineglass Metering is recruiting a Firmware Validation Engineer for Release Verification in Kitchener, Ontario, Canada. The onsite, full-time senior engineer owns the firmware release matrix across logger boards, bootloader versions, and sensor configurations. The role expands hardware-in-loop regression for wake, sleep, brownout, and update-recovery paths and reproduces board failures with serial traces and laboratory instruments before release sign-off. Firmware validation ownership is critical. Hardware-in-loop integration testing and instrumented board debugging are required. C driver knowledge and RTOS timing context are preferred. The employer confirms work authorization support for the stated location, and the advertisement was published on 2026-07-07. Pineglass releases utility hardware quarterly and expects validation to block a release when a reproducible field fault remains open. Test evidence must identify the board revision, firmware build, setup, observed result, and disposition.""",
46: """Westhaven Power Assemblies is seeking an Electrical Hardware Design Engineer for its Power Electronics Design team in Burlington, Ontario, Canada. This onsite, full-time senior position owns schematics and PCB layout for high-voltage power-conversion assemblies. It leads electrical safety, EMC, and thermal compliance testing for new assemblies and approves component substitutions and manufacturing release packages with suppliers. High-voltage schematic and PCB design ownership is critical. Electrical compliance testing and supplier release are required. Firmware collaboration is preferred but is not the primary responsibility. Westhaven confirms work authorization support for the stated location, and the role was published on 2026-07-06. The design group works from electrical requirements through manufacturing release, balancing thermal margins, component availability, and documented compliance results. Candidates will spend most of their time in electrical design reviews and supplier decisions rather than firmware bring-up or embedded test automation.""",
47: """Cobalt Orchard Software is hiring a Product Software Engineer for its Connected Applications team in Toronto, Ontario, Canada. The remote, full-time mid-level role builds customer-facing web services and TypeScript interfaces for device account management. It operates cloud APIs, dashboards, and alerting for connected-device usage data, then partners with product managers on feature delivery, documentation, and support rotations. Web-service ownership is critical. Cloud API delivery and operational support are required. Interest in embedded devices is preferred but does not define the work. The employer confirms work authorization support for the stated location; this advertisement was published on 2026-07-05. Cobalt Orchard sells connected-device management software, and the application team measures API reliability, user workflows, and cloud incidents. It does not own firmware, boards, peripheral drivers, real-time scheduling, or hardware-in-loop verification. The team works with device specialists through documented service contracts and release checklists.""",
48: """Mariner Access Controls is hiring an Embedded Systems Engineer for Secure Device Firmware in Seattle, Washington, United States. This onsite, full-time mid-level role implements secure boot and signed firmware updates for access-control controllers, maintains C drivers for CAN-connected locks and tamper sensors, and supports federal customer certification tests at the Seattle laboratory. Secure firmware and CAN driver work are required, and RTOS experience is preferred. The employer requires United States work authorization and customer clearance for engineers entering the federal test laboratory; sponsorship is not available. The posting was published on 2026-07-04. The team records update verification, tamper-sensor behavior, and certification findings against each controller revision. This position is subject to the laboratory's access process and spends time between firmware review, bus diagnosis, and customer test support. Candidates must be able to satisfy the stated authorization and clearance conditions before entering the lab.""",
49: """Signal North Automation is looking for a Staff Firmware Architect in its Firmware Architecture organization in Toronto, Ontario, Canada. The hybrid, full-time staff role sets firmware architecture standards across six product lines, resolves cross-team design disputes, mentors senior engineers, leads hiring panels, and establishes a multi-year technical roadmap. It also owns portfolio-level firmware risk reviews with product and manufacturing executives. Staff-level cross-product architecture authority is critical. Cross-team architecture influence and roadmap ownership are required, while C driver experience is preferred. The employer confirms work authorization support for the stated location, and the advertisement was published on 2026-07-03. Signal North is recruiting an architect to govern several firmware organizations rather than an engineer focused on one board or release train. The role writes standards, mediates decisions, and communicates portfolio risk to senior stakeholders across product and manufacturing.""",
50: """Maple Tide Sensors is seeking an Embedded Test Engineer for its Device Quality team. The advertisement describes remote work within Canada, but the city and sponsorship policy are not stated. The full-time assignment creates regression checks for sensor devices, summarizes failures for firmware developers, reproduces intermittent bus faults on evaluation boards when laboratory access is available, and maintains test results and release notes for a connected-device portfolio. Embedded-device testing is critical. Bus-level debugging and reproducible test work are required; Python automation depth is required for repeatable device regression, and Python test tooling is preferred. The posting does not state the role level or posting date. Maple Tide's shortened notice gives no definitive location beyond Canada and no authorization policy, so those details require confirmation. The test engineer will preserve board setup, firmware version, observed behavior, and disposition for each failure before a release review.""",
51: """Ironleaf Appliance Systems is hiring a Systems Integration Engineer for Connected Product Integration in Toronto, Ontario, Canada. This hybrid, full-time mid-level role integrates appliance sensors, actuator commands, and CAN messages during system bring-up. The engineer maintains interface-control checks and requirements traceability across electrical and software boundaries, then uses a Python data-acquisition bench to reproduce faults and document root-cause findings. Sensor, actuator, and interface integration ownership is critical. Requirements traceability and test-bench execution plus cross-functional release coordination are required. Hardware-in-loop controls testing and MATLAB analysis are preferred. Ironleaf confirms work authorization support for the stated location; the posting was published on 2026-07-02. Systems engineers work inside electrical, mechanical, and software release teams and carry a failure from first observation to a reproducible correction. Release records identify the interface, evidence collected, owner, and verification result.""",
52: """Blue Current Medical Devices is recruiting a Verification and Test Engineer for Product Verification in Mississauga, Ontario, Canada. The onsite, full-time senior position builds verification plans for sensor, actuator, and communications interfaces on a regulated device. It links requirements to test evidence, presents open risks at design-control reviews, operates data-acquisition benches, and investigates failures with electrical and software partners. Verification planning and traceability are critical. Test-bench execution, failure investigation, electrical and software collaboration, and ownership of medical-device design-control documentation and regulated risk files are required. CAN interface testing and hardware-in-loop experience are preferred. The employer confirms work authorization support for the stated location, and the job was published on 2026-07-01. Blue Current expects every result to be attributable to a requirement, configuration, procedure, and recorded outcome. Engineers prepare review material, preserve unresolved risks, and work across disciplines when a bench failure cannot be isolated by software logs alone.""",
53: """Mosaic Transit Controls needs a Controls Validation Engineer for Vehicle Controls Validation in Ottawa, Ontario, Canada. This hybrid, full-time senior role validates control-loop behavior for steering and thermal actuators on a transit demonstrator. The engineer designs hardware-in-loop scenarios for sensor dropouts, saturation, and recovery behavior and analyzes Python and MATLAB test data to publish acceptance decisions for the controls release. Control-system validation ownership is critical. Hardware-in-loop control testing and Python or MATLAB test analysis are required. CAN integration knowledge and requirements traceability are preferred. Mosaic confirms work authorization support for the stated location; the posting was published on 2026-06-30. The controls laboratory turns scenario definitions into repeatable runs and reports whether the observed response meets the release threshold. Engineers document setup changes, investigate unexpected transients, and present evidence to the vehicle integration review.""",
54: """Copper Meadow Robotics is hiring a Hardware Bring-Up Engineer for Prototype Integration in Guelph, Ontario, Canada. This onsite, full-time mid-level role brings up sensor and actuator assemblies on prototype appliance-control hardware. It traces CAN and power-interface failures with bench instruments and captured data, then packages reproducible findings for electrical, mechanical, and firmware teams before build handoff. Prototype hardware bring-up and interface debugging are critical. Bench-based data collection and root-cause analysis and cross-functional handoff with electrical and firmware teams are required. Hardware-in-loop testing and requirements traceability are preferred. The employer confirms work authorization support for the stated location, and the posting was published on 2026-06-29. Copper Meadow builds prototype inspection cells in Guelph; the engineer moves between a wiring bench, test stand, and release room. A useful handoff includes the failed interface, captured signal, attempted correction, and next verification action.""",
55: """Prairie Forge Appliances is looking for a Manufacturing Test Engineer for Factory Test Engineering in Cambridge, Ontario, Canada. The onsite, full-time mid-level engineer designs manufacturing test fixtures for sensor calibration and actuator end-of-line checks. The role uses Python data collection to identify yield shifts, separates fixture faults from product defects, writes controlled work instructions, and trains operators before a station enters production. Data acquisition and root-cause analysis and controlled validation and production release practice are required. Industrial or CAN protocol experience and requirements traceability are preferred. Manufacturing test ownership is critical to the factory-test team. Prairie Forge confirms work authorization support for the stated location; the advertisement was published on 2026-06-28. The connected cooking line is moving into higher volume, so the engineer must turn station data into release actions, preserve revision history, and coordinate corrections with manufacturing, quality, and product engineering.""",
56: """Lake Basin Structures is hiring a Mechanical Design Engineer for Industrial Chassis Design in Toronto, Ontario, Canada. This hybrid, full-time senior role creates detailed CAD assemblies and tolerance drawings for sheet-metal industrial enclosures. The engineer leads mechanical prototype builds, fit checks, and supplier drawing reviews and owns structural and thermal design changes through manufacturing release. Mechanical CAD and enclosure-design ownership are critical. Mechanical prototype and manufacturing release work are required. Systems-test collaboration is preferred but does not replace mechanical design ownership. The employer confirms work authorization support for the stated location, and the posting was published on 2026-06-27. Lake Basin's designers work with fabricators and manufacturing engineers on tolerances, material choices, and drawing revisions. The day-to-day work is mechanical design and supplier release; sensor testing, controls validation, and software test evidence are outside the core assignment.""",
57: """Silver Birch Software is seeking a Technical Program Manager, Connected Products, for its Platform Programs team in Toronto, Ontario, Canada. The remote, full-time senior role owns cross-team software roadmaps, delivery milestones, and executive status reviews. It coordinates cloud vendors, contract developers, and product launch dependencies, then maintains program risks, budget forecasts, and decision logs for connected-product leadership. Program roadmap and delivery ownership are critical. Executive reporting and vendor coordination are required. Hardware context is preferred but does not make this a verification role. Silver Birch confirms work authorization support for the stated location; the advertisement was published on 2026-06-26. This program office manages delivery commitments, dependencies, budgets, and escalations from a remote platform organization. It does not design test benches, run control experiments, perform hardware bring-up, or own release verification. The manager keeps partners aligned through status reviews and documented decisions.""",
58: """Aurora Gate Instruments is recruiting a Systems Verification Engineer for Regulated Systems Assurance in Toronto, Ontario, Canada. The hybrid, full-time senior engineer leads verification for safety-critical instruments and approves release evidence for customer audits. The role interprets formal requirements, signs compliance decisions with the responsible engineer, and coordinates root-cause investigations across electrical, mechanical, and software teams. A current Professional Engineer license is mandatory for regulated release sign-off. Formal verification planning and release sign-off are required, and Python test tooling is preferred. The employer confirms work authorization support for the stated location; this posting was published on 2026-06-25. Aurora Gate's assurance team preserves traceability from requirement through procedure, result, deviation, and approval. The position carries regulated customer-facing authority and requires the professional credential before an engineer may approve a release package. Investigation work includes collecting evidence from each participating discipline and documenting the corrective verification path.""",
59: """West Coast Motion Labs is seeking a Principal Controls Verification Lead for Controls Assurance in Toronto, Ontario, Canada. This hybrid, full-time lead position sets controls-assurance strategy across several programs, negotiates verification commitments with customers, leads a group of verification engineers, approves staffing plans, coaches technical leads, and presents program-level residual risk and release recommendations to executive steering committees. Principal-level organizational and customer-facing assurance ownership is critical. People leadership and program-level risk ownership are required, while hardware-in-loop controls testing is preferred. The employer confirms work authorization support for the stated location, and the advertisement was published on 2026-06-24. West Coast Motion Labs expects organization-wide authority over controls assurance rather than an individual contributor validation assignment. The lead sets commitments, decides how risk is escalated, and represents release evidence to customers and executives across multiple programs.""",
60: """Willow Current Works is hiring a Systems Test Engineer for Systems Test. The shortened notice describes remote work within Canada, but the role level and authorization policy are not stated. The full-time engineer executes system tests for sensors, actuators, and interface changes on a connected product, records results, opens reproducible defects for the next integration build, and commissions and calibrates physical actuator control benches, including loop tuning and instrumentation setup, during scheduled verification activities. System verification is critical. Test traceability and bench data collection are required, as are commissioning and calibration of physical actuator control benches, loop tuning, and instrumentation setup. CAN or industrial-protocol testing is preferred. The posting date, exact remote geography, level, and authorization policy are omitted and require confirmation. Willow expects test records to identify the configuration, procedure, observed behavior, and next owner. The role may involve collaboration with controls, electrical, mechanical, and software engineers, but the abbreviated notice does not establish the full scope or eligibility conditions.""",
}
DESCRIPTION_COPY[32] = DESCRIPTION_COPY[32].replace("The employer confirms work authorization support for the stated location.", "Copper Finch's hiring policy confirms work authorization support for the Waterloo laboratory.")
DESCRIPTION_COPY[34] = DESCRIPTION_COPY[34].replace("The employer confirms work authorization support for the stated location.", "Lumen Orchard confirms work authorization support for its Vancouver engineering team.")
DESCRIPTION_COPY[37] = DESCRIPTION_COPY[37].replace("The employer confirms work authorization support for the stated location.", "Morrow Field confirms work authorization support for the Calgary platform office.")
DESCRIPTION_COPY[39] = DESCRIPTION_COPY[39].replace("The employer confirms work authorization support for the stated location.", "Cedar Relay confirms work authorization support for the Toronto headquarters.")
DESCRIPTION_COPY[37] = DESCRIPTION_COPY[37].replace("scenario coverage", "test-condition coverage")
DESCRIPTION_COPY[53] = DESCRIPTION_COPY[53].replace("scenario definitions", "test definitions")
DESCRIPTION_COPY[46] = DESCRIPTION_COPY[46].replace("Candidates will spend", "Engineers will spend")
DESCRIPTION_COPY[48] = DESCRIPTION_COPY[48].replace("Candidates must be able", "Engineers must be able")


POSTING_DATES = {
    31: "2026-07-20", 32: "2026-07-18", 33: "2026-07-19",
    34: "2026-07-17", 35: "2026-07-16", 36: "2026-07-15", 37: "2026-07-14", 38: "2026-07-13", 39: "2026-07-12",
    41: "2026-07-11", 42: "2026-07-10", 43: "2026-07-09", 44: "2026-07-08", 45: "2026-07-07", 46: "2026-07-06", 47: "2026-07-05",
    48: "2026-07-04", 49: "2026-07-03",
    51: "2026-07-02", 52: "2026-07-01", 53: "2026-06-30", 54: "2026-06-29", 55: "2026-06-28", 56: "2026-06-27", 57: "2026-06-26", 58: "2026-06-25", 59: "2026-06-24",
}

AUTHORIZATION_STATEMENTS = {
    31: "The employer confirms work authorization support for the stated location.",
    32: "The employer confirms work authorization support for the stated location.",
    33: "The employer confirms work authorization support for the stated location.",
    34: "The employer confirms work authorization support for the stated location.",
    35: "The employer confirms work authorization support for the stated location.",
    36: "United States work authorization without sponsorship is required for the laboratory assignment.",
    37: "The employer confirms work authorization support for the stated location.",
    38: "The employer confirms work authorization support for the stated location.",
    39: "The employer confirms work authorization support for the stated location.",
    40: "Authorization and sponsorship policy are unknown in the posting.",
    41: "The employer confirms work authorization support for the stated location.",
    42: "The employer confirms work authorization support for the stated location.",
    43: "The employer confirms work authorization support for the stated location.",
    44: "The employer confirms work authorization support for the stated location.",
    45: "The employer confirms work authorization support for the stated location.",
    46: "The employer confirms work authorization support for the stated location.",
    47: "The employer confirms work authorization support for the stated location.",
    48: "United States work authorization and customer clearance are required, and sponsorship is not available.",
    49: "The employer confirms work authorization support for the stated location.",
    50: "Authorization and sponsorship policy are unknown in the posting.",
    51: "The employer confirms work authorization support for the stated location.",
    52: "The employer confirms work authorization support for the stated location.",
    53: "The employer confirms work authorization support for the stated location.",
    54: "The employer confirms work authorization support for the stated location.",
    55: "The employer confirms work authorization support for the stated location.",
    56: "The employer confirms work authorization support for the stated location.",
    57: "The employer confirms work authorization support for the stated location.",
    58: "The employer confirms work authorization support for the stated location.",
    59: "The employer confirms work authorization support for the stated location.",
    60: "Authorization policy is unknown in the posting.",
}


POSITIVE_REASONS = {
    31: ("runtime_ownership", "The profile demonstrates C++ ROS 2 localization-runtime maintenance, and the posting assigns synchronized pose and route-plan updates.", ["e1", "ros-runtime"]),
    32: ("integration_boundary", "The profile demonstrates localization, sensor-frame calibration, and simulation safety checks, and the posting assigns vehicle-wide package integration.", ["e1", "e2", "e5", "stack-integration"]),
    33: ("mapping_ownership", "The profile demonstrates localization maintenance, measured frame calibration, and Linux replay debugging, and the posting assigns map-quality ownership.", ["e1", "e2", "e4", "mapping-pipeline"]),
    34: ("perception_handoff", "The profile demonstrates camera-package integration without model-training ownership, and the posting assigns perception handoff testing across navigation interfaces.", ["e3", "perception-interfaces", "sensor-checks"]),
    35: ("operational_data_overlap", "The profile demonstrates Linux replay tooling during autonomous field runs, and robotics telemetry is peripheral context; this overlap does not overcome the decisive data-platform boundary.", ["e4", "robotics-data"]),
    36: ("test_lab_overlap", "The profile's automated simulation safety checks match the posting's critical simulation-safety qualification; this technical overlap is peripheral and does not overcome the unsupported production controls-validation boundary.", ["e5", "simulation-safety"]),
    37: ("simulation_delivery", "The profile demonstrates simulation safety checks and Linux replay debugging, and the posting assigns robotics simulation release work.", ["e5", "e4", "sim-platform"]),
    38: ("field_reliability", "The profile demonstrates Linux field replay and safety-check automation, and the posting assigns incident investigation for supervised fleet runs.", ["e4", "e5", "fleet-debugging"]),
    39: ("autonomy_context", "The profile demonstrates ROS 2 runtime work, and the preferred robotics-software familiarity is peripheral context; this overlap does not overcome the decisive leadership-scope gap.", ["e1", "ros2"]),
    40: ("robotics_integration", "The profile demonstrates C++ ROS 2 integration and sensor calibration, and the posting assigns mobile-robot prototype integration.", ["e1", "e2", "robotics-integration"]),
    41: ("firmware_drivers", "The profile demonstrates C peripheral-driver ownership, FreeRTOS scheduling, and board debugging, and the posting assigns logger firmware lifecycle work.", ["e1", "e2", "e3", "driver-ownership"]),
    42: ("driver_support", "The profile demonstrates SPI, I2C, UART, and board-bring-up work, and the posting assigns connectivity-driver and board-support maintenance.", ["e1", "e3", "bus-drivers"]),
    43: ("realtime_firmware", "The profile demonstrates FreeRTOS timing and memory work plus bootloader release practice, and the posting assigns constrained-controller recovery behavior.", ["e2", "e4", "rtos-components"]),
    44: ("edge_integration", "The profile demonstrates board diagnostics, bootloader updates, and hardware-in-loop testing, and the posting includes device-boundary integration checks.", ["e3", "e4", "e5", "integration-lab"]),
    45: ("release_validation", "The profile demonstrates hardware-in-loop regression, instrumented board debugging, and bootloader release practice, and the posting assigns firmware release verification.", ["e3", "e4", "e5", "release-matrix"]),
    46: ("bench_context", "The profile demonstrates prototype board bring-up with lab instruments, and firmware collaboration is peripheral context; this overlap does not overcome the unsupported electrical-design core.", ["e3", "firmware"]),
    47: ("embedded_testing", "The profile demonstrates embedded unit, integration, and hardware-in-loop testing, and embedded-device interest is peripheral context; this overlap does not overcome the unsupported application core.", ["e5", "embedded-devices"]),
    48: ("firmware_context", "The profile demonstrates C peripheral drivers and board diagnostics, and the posting assigns secure controller firmware and CAN-connected device work.", ["e1", "e3", "secure-firmware"]),
    49: ("firmware_architecture_context", "The profile demonstrates C-driver work, and the preferred C-driver experience is peripheral context; this overlap does not overcome the decisive staff-scope gap.", ["e1", "c-drivers"]),
    50: ("device_testing", "The profile demonstrates embedded hardware-in-loop tests and board fault tracing, and the posting assigns sensor-device regression work.", ["e5", "e3", "device-regression"]),
    51: ("systems_integration", "The profile demonstrates sensor and actuator bring-up, requirements traceability, Python data acquisition, and cross-functional release work, and the posting assigns connected-product integration.", ["e1", "e2", "e3", "e5", "sensor-actuator"]),
    52: ("verification_planning", "The profile demonstrates traceability, data-acquisition benches, control-loop testing, and cross-team defect work, and the posting assigns regulated verification planning.", ["e2", "e3", "e4", "verification-plan"]),
    53: ("controls_validation", "The profile demonstrates control-loop and hardware-in-loop testing with MATLAB and Python analysis, and the posting assigns actuator validation scenarios.", ["e3", "e4", "control-tests"]),
    54: ("hardware_bringup", "The profile demonstrates sensor and actuator integration, a Python data-acquisition bench, and cross-functional release handoffs, and the posting assigns prototype bring-up.", ["e1", "e3", "e5", "prototype-bringup"]),
    55: ("test_data_context", "The profile demonstrates Python data acquisition and control-test evidence, and the posting assigns fixture data collection for a factory line.", ["e3", "e4", "yield-analysis"]),
    56: ("systems_test_context", "The profile demonstrates cross-functional release coordination, and the posting includes systems-test collaboration for an industrial chassis.", ["e5", "systems-testing"]),
    57: ("release_coordination", "The profile demonstrates cross-functional release coordination, and hardware context is peripheral context; this overlap does not overcome the decisive management-scope gap.", ["e5", "hardware-context"]),
    58: ("verification_context", "The profile demonstrates requirements traceability, Python bench investigation, and cross-functional root-cause work, and the posting assigns regulated verification evidence.", ["e2", "e3", "failure-investigation"]),
    59: ("controls_test_context", "The profile demonstrates hardware-in-loop controls testing, and the preferred HIL qualification is peripheral context; this overlap does not overcome the decisive lead-scope gap.", ["e4", "hil"]),
    60: ("system_test_work", "The profile demonstrates requirements traceability, Python data acquisition, and hardware-in-loop control testing, and the posting assigns connected-product system tests.", ["e2", "e3", "e4", "system-tests"]),
}


# Explicit material-gap authority.  A reference token is resolved only to an
# already-authored atomic fact or profile-level fact; no gap is inferred from
# grade, category, case number, or missing evidence.
GAP_PLANS = {
    34: [("insufficient_evidence", "The profile demonstrates perception integration and Linux field replay, but the reviewed evidence does not establish production ownership of perception-runtime latency investigation during on-robot deployments.", "runtime-performance", ["e3", "e4"])],
    35: [("critical_gap", "The reviewed profile has no demonstrated ownership of the SQL warehouse models named by this posting.", "sql-platform", []), ("required_gap", "The reviewed profile has no demonstrated ownership of scheduled production data-pipeline operations.", "pipeline-operations", [])],
    36: [("required_gap", "The profile contains controls coursework and simulation safety work, but no demonstrated production controls-validation ownership for actuator release.", "controls-validation", ["e7", "e5"])],
    37: [("critical_gap", "The profile does not demonstrate the staff-level architecture and organizational authority required by this simulation platform role.", "staff-authority", ["@level", "@target", "@duration"])],
    39: [("critical_gap", "The profile does not demonstrate director-level portfolio and organizational leadership for a multi-product autonomy organization.", "portfolio-leadership", ["@level", "@target", "@duration"]), ("required_gap", "The profile does not demonstrate executive stakeholder influence or multi-team planning at the stated scope.", "executive-influence", ["@level", "@target", "@duration"])],
    44: [("critical_gap", "No reviewed evidence demonstrates ownership of an embedded Linux image and its user-space service boundary.", "embedded-linux", [])],
    46: [("critical_gap", "No reviewed evidence demonstrates high-voltage schematic or PCB design ownership.", "electrical-design", []), ("required_gap", "No reviewed evidence demonstrates electrical compliance testing or supplier release authority.", "compliance", [])],
    47: [("critical_gap", "No reviewed evidence demonstrates web-service ownership for the customer application.", "web-platform", []), ("required_gap", "No reviewed evidence demonstrates cloud API delivery or operational support ownership.", "cloud-operations", [])],
    49: [("critical_gap", "The profile does not demonstrate staff-level cross-product firmware architecture authority.", "staff-architecture", ["@level", "@target", "@duration"]), ("required_gap", "The profile does not demonstrate portfolio-level architecture influence or roadmap ownership.", "portfolio-influence", ["@level", "@target", "@duration"])],
    55: [("critical_gap", "No reviewed evidence demonstrates manufacturing test ownership for fixture design and end-of-line release.", "manufacturing-test", [])],
    56: [("critical_gap", "No reviewed evidence demonstrates mechanical CAD and enclosure-design ownership.", "mechanical-design", []), ("required_gap", "No reviewed evidence demonstrates mechanical prototype or manufacturing-release ownership.", "manufacturing-release", [])],
    57: [("critical_gap", "No reviewed evidence demonstrates program-roadmap and delivery ownership.", "program-management", []), ("required_gap", "No reviewed evidence demonstrates executive reporting or vendor coordination.", "executive-reporting", [])],
    58: [("critical_gap", "The reviewed profile has an explicit confirmed-none professional-license status, so it cannot establish the mandatory release-sign-off credential.", "professional-license", ["@license"])],
    59: [("critical_gap", "The profile does not demonstrate principal-level organizational and customer-facing assurance authority.", "principal-scope", ["@level", "@target", "@duration"]), ("required_gap", "The profile does not demonstrate people leadership or program-level risk ownership at the stated scope.", "team-leadership", ["@level", "@target", "@duration"])],
    50: [("insufficient_evidence", "The profile demonstrates embedded Python test use, but the reviewed evidence does not establish deeper ownership of a maintained Python automation suite for repeatable device regression.", "python-automation", ["e5"])],
    40: [("insufficient_evidence", "Simulation checks and controls coursework provide transferable context, but they do not establish production actuator-interface integration or controls-debugging ownership during prototype trials.", "actuator-controls-integration", ["e5", "e7"])],
    42: [("insufficient_evidence", "The profile demonstrates production C drivers and RTOS timing work, but the reviewed evidence does not explicitly establish ownership of interrupt/DMA concurrency and high-rate peripheral fault handling.", "interrupt-dma-depth", ["e1", "e2"])],
    52: [("insufficient_evidence", "The profile demonstrates traceability and cross-functional release work, but the reviewed evidence does not explicitly establish ownership of medical-device design-control documentation and regulated risk files.", "design-control-depth", ["e2", "e5"])],
    60: [("insufficient_evidence", "The profile demonstrates a Python data-acquisition bench and control-loop hardware-in-loop testing, but the reviewed evidence does not establish full physical-bench commissioning, calibration, loop tuning, and instrumentation setup ownership.", "bench-commissioning", ["e3", "e4"])],
}


RATIONALES = {
    31: "calibration-031 is Excellent because C++ ROS 2 runtime maintenance, sensor-health integration, and Linux field replay are directly demonstrated for the named responsibilities; there is no substantive gap, and the posting is eligible and non-provisional.",
    32: "calibration-032 is Excellent because the profile directly covers ROS 2 integration, frame calibration, and simulation safety gates for the vehicle lab; there is no substantive gap, and eligibility is confirmed.",
    33: "calibration-033 is Excellent because localization ownership, coordinate-frame calibration, and Linux replay analysis directly cover the map-quality responsibilities; there is no substantive gap, and eligibility is confirmed.",
    34: "calibration-034 is Good because perception-package integration, ROS 2 interface debugging, timestamp and frame validation, and Linux field-log analysis directly cover the handoff work without claiming model-training ownership; the limited runtime-performance ownership depth is recorded separately, and eligibility is confirmed.",
    35: "calibration-035 is Don't Match because the posting's core work is data-platform ownership while the profile offers only peripheral Linux field-debugging context; the SQL and pipeline requirements are grounded gaps, and eligibility is otherwise confirmed.",
    36: "calibration-036 is Don't Match because United States authorization without sponsorship is a hard eligibility conflict; controls coursework and simulation checks provide context but not production actuator-validation ownership, and the technical limitation is recorded separately.",
    37: "calibration-037 is Don't Match because the staff architecture and cross-product authority exceed the confirmed mid-to-senior target and demonstrated scope; the posting is level-ineligible, and the scope gaps are separate from simulation evidence.",
    38: "calibration-038 is Excellent because field incident debugging, Linux replay, and safety verification directly cover the fleet reliability responsibilities; there is no substantive gap, and eligibility is confirmed.",
    39: "calibration-039 is Don't Match because director-level portfolio and executive scope exceed the candidate's target levels and demonstrated responsibility; the level conflict is hard, with the missing portfolio scope recorded explicitly.",
    40: "calibration-040 is Weak because C++ ROS 2 integration, sensor calibration, Linux field debugging, and mobile-robot integration match the critical robotics core, while actuator-interface integration and production controls debugging remain insufficiently demonstrated; eligibility remains unknown and the proposal is provisional.",
    41: "calibration-041 is Excellent because C drivers, FreeRTOS scheduling, board bring-up, and hardware-in-loop testing directly cover the logger firmware lifecycle; there is no substantive gap, and eligibility is confirmed.",
    42: "calibration-042 is Good because C peripheral drivers for SPI, I2C, and UART, board-support verification, and embedded testing directly cover the connectivity role; the limited interrupt/DMA and high-rate fault-handling depth is recorded separately, and eligibility is confirmed.",
    43: "calibration-043 is Excellent because constrained-resource FreeRTOS work, bootloader recovery, and board diagnostics directly cover the real-time firmware duties; there is no substantive gap, and eligibility is confirmed.",
    44: "calibration-044 is Don't Match because embedded Linux image ownership is a critical day-to-day responsibility with no demonstrated evidence; firmware updates and lab testing are adjacent but cannot replace that missing core ownership.",
    45: "calibration-045 is Excellent because release-matrix ownership, hardware-in-loop regression, and instrumented board debugging directly cover firmware validation; there is no substantive gap, and eligibility is confirmed.",
    46: "calibration-046 is Don't Match because the posting is centered on high-voltage electrical design and compliance authority, while the profile demonstrates only board bring-up and instrumentation; the critical and required design gaps are explicit.",
    47: "calibration-047 is Don't Match because the day-to-day work is web-service and cloud application delivery, while the profile supplies embedded test context only; the core software responsibilities are unsupported.",
    48: "calibration-048 is Don't Match. Substantively, C peripheral drivers, board diagnostics, secure controller firmware, and CAN-connected device work align directly with the profile. The Seattle position requires United States work authorization without sponsorship, conflicting with the candidate's confirmed Canada-only authorization.",
    49: "calibration-049 is Don't Match because staff-level cross-product architecture and portfolio scope exceed the confirmed target levels and demonstrated ownership; the level conflict and scope gaps are explicit.",
    50: "calibration-050 is Weak because embedded test execution and Python use are directly relevant, but deeper ownership of a maintained Python automation suite remains insufficiently demonstrated; eligibility is unknown and the proposal is provisional.",
    51: "calibration-051 is Excellent because sensor and actuator integration, interface traceability, Python data acquisition, and cross-functional release work directly cover the systems role; there is no substantive gap, and eligibility is confirmed.",
    52: "calibration-052 is Good because verification planning, requirements traceability, data-acquisition bench investigation, and electrical/software collaboration directly cover the regulated-device responsibilities; medical-device design-control and risk-file ownership depth remains insufficiently demonstrated, and eligibility is confirmed.",
    53: "calibration-053 is Excellent because control-loop validation, hardware-in-loop scenarios, and Python/MATLAB analysis directly cover the transit controls work; there is no substantive gap, and eligibility is confirmed.",
    54: "calibration-054 is Excellent because prototype bring-up, CAN and power-interface debugging, data collection, and cross-team handoff directly cover the integration role; there is no substantive gap, and eligibility is confirmed.",
    55: "calibration-055 is Don't Match because manufacturing-test ownership is the critical day-to-day assignment and no reviewed evidence establishes fixture or end-of-line ownership; related data-acquisition experience is not enough to cover that core responsibility.",
    56: "calibration-056 is Don't Match because the job is mechanical CAD, prototype, and manufacturing-release work, while the profile offers only cross-functional release context; the central mechanical qualifications are unsupported.",
    57: "calibration-057 is Don't Match because the job owns program delivery, vendor coordination, and executive reporting rather than systems verification; the profile's cross-functional release work is only peripheral context.",
    58: "calibration-058 is Don't Match because a current professional license is mandatory for regulated release sign-off and the explicit profile-level license status is confirmed none; the verification evidence is relevant but cannot satisfy the credential conflict.",
    59: "calibration-059 is Don't Match because principal-level controls-assurance authority and people leadership exceed the confirmed target levels and demonstrated scope; the hard level conflict is grounded by the exact posting scope.",
    60: "calibration-060 is Weak because requirements traceability, Python data acquisition, and control-loop hardware-in-loop testing match system verification, while physical actuator-bench commissioning, calibration, loop tuning, and instrumentation setup remain insufficiently demonstrated; eligibility remains unknown and the proposal is provisional.",
}
for _case_number, _closing in {
    31: "Eligibility is confirmed and the proposal is not provisional.",
    32: "The Waterloo hiring facts are confirmed, with no provisional uncertainty.",
    33: "The Montreal posting is eligible and complete for this substantive assessment.",
    34: "The interface posting is eligible, dated, and complete for the known work.",
    38: "The Ottawa fleet-reliability posting has confirmed eligibility and no provisional flag.",
    41: "The logger role is eligible with no unresolved posting facts.",
    42: "The Hamilton driver role is eligible and fully specified.",
    43: "The real-time firmware role is eligible and not provisional.",
    45: "The Kitchener validation role is eligible and fully specified.",
    51: "The Toronto integration role is eligible and carries no provisional uncertainty.",
    52: "The regulated-device posting is eligible and fully specified.",
    53: "The Ottawa controls posting is eligible and not provisional.",
    54: "The Guelph bring-up role is eligible with complete known posting facts.",
}.items():
    RATIONALES[_case_number] = RATIONALES[_case_number].replace(
        "there is no substantive gap, and the posting is eligible and non-provisional.",
        _closing,
    ).replace(
        "there is no substantive gap, and eligibility is confirmed.",
        _closing,
    )


ELIGIBILITY_PLANS = {
    31: ("eligible_facts", "A Toronto hybrid mid-level posting states supported authorization and a location and level within the confirmed preferences.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    32: ("eligible_facts", "A Waterloo onsite mid-level posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    33: ("eligible_facts", "A Montreal hybrid senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    34: ("eligible_facts", "A Vancouver hybrid mid-level posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    35: ("eligible_facts", "A Toronto remote senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    36: ("hard_authorization_conflict", "The Austin posting requires United States work authorization without sponsorship, while the confirmed candidate authorization is Canada-only and the profile does not require sponsorship for Canada.", ["@location", "@authorization", "@pref_auth"]),
    37: ("hard_level_conflict", "The Calgary posting requires staff-level authority, while the candidate targets junior, mid, and senior levels; the candidate's 3.5 years do not establish the stated staff scope.", ["@level", "@pref_level", "@duration", "staff-authority"]),
    38: ("eligible_facts", "An Ottawa hybrid senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    39: ("hard_level_conflict", "The Toronto posting requires director-level portfolio authority and organizational scope, while the candidate targets junior, mid, and senior levels; the candidate's 3.5 years do not establish that director scope.", ["@level", "@pref_level", "@duration", "portfolio-leadership", "executive-influence"]),
    40: ("eligibility_unknown", "The remote-within-Canada posting leaves city, authorization, level, and posting date unresolved; candidate authorization and target-level facts are known but cannot resolve those missing posting facts.", ["@location", "@authorization", "@date", "@level", "@pref_auth", "@pref_level"]),
    41: ("eligible_facts", "A Toronto hybrid mid-level posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    42: ("eligible_facts", "A Hamilton onsite mid-level posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    43: ("eligible_facts", "A London hybrid senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    44: ("eligible_facts", "A Toronto hybrid mid-level posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    45: ("eligible_facts", "A Kitchener onsite senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    46: ("eligible_facts", "A Burlington onsite senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    47: ("eligible_facts", "A Toronto remote mid-level posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    48: ("hard_authorization_conflict", "The Seattle posting requires United States work authorization without sponsorship, while the confirmed candidate authorization is Canada-only.", ["@location", "@authorization", "@pref_auth"]),
    49: ("hard_level_conflict", "The Toronto posting requires staff-level cross-product architecture and portfolio influence, while the candidate targets junior, mid, and senior levels; the candidate's 4 years do not establish the stated staff scope.", ["@level", "@pref_level", "@duration", "staff-architecture", "portfolio-influence"]),
    50: ("eligibility_unknown", "The remote-within-Canada posting leaves city, sponsorship, level, and posting date unresolved; candidate authorization and target-level facts are known but cannot resolve those missing posting facts.", ["@location", "@authorization", "@date", "@level", "@pref_auth", "@pref_level"]),
    51: ("eligible_facts", "A Toronto hybrid mid-level posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    52: ("eligible_facts", "A Mississauga onsite senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    53: ("eligible_facts", "An Ottawa hybrid senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    54: ("eligible_facts", "A Guelph onsite mid-level posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    55: ("eligible_facts", "A Cambridge onsite mid-level posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    56: ("eligible_facts", "A Toronto hybrid senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    57: ("eligible_facts", "A Toronto remote senior posting states supported authorization and fits the confirmed location and target level.", ["@location", "@authorization", "@level", "@pref_auth", "@pref_level"]),
    58: ("hard_license_conflict", "The Toronto posting requires a current Professional Engineer license, while the explicit profile-level license status is confirmed none; academic education is not used as proof of licensure.", ["professional-license", "@license"]),
    59: ("hard_level_conflict", "The Toronto posting requires principal-level organizational and customer-facing controls authority, while the candidate targets junior, mid, and senior levels; the candidate's 5 years do not establish that principal scope.", ["@level", "@pref_level", "@duration", "principal-scope", "team-leadership"]),
    60: ("eligibility_unknown", "The remote-within-Canada posting leaves exact geography, authorization, level, and posting date unresolved; candidate authorization and target-level facts are known but cannot resolve those missing posting facts.", ["@location", "@authorization", "@date", "@level", "@pref_auth", "@pref_level"]),
}


def _profile(profile_ref: str) -> dict[str, object]:
    source = PROFILES[profile_ref]
    evidence = []
    for ident, kind, statement, capabilities, technologies in source["items"]:
        evidence.append({
            "evidence_id": f"profile:{profile_ref}:{ident}",
            "statement": statement,
            "evidence_kind": kind,
            "evidence_quality": "verified" if kind == "demonstrated" else "self_reported",
            "provenance": f"reviewed-deidentified-{profile_ref}-{ident}",
            "demonstrated": kind in {"demonstrated", "transferable_demonstrated"},
            "capabilities": capabilities,
            "technologies": technologies,
        })
    profile_fields = {
        "cal-profile-05": {"clearance_status": "none_recorded"},
        "cal-profile-06": {"professional_license_status": "confirmed_none"},
    }.get(profile_ref, {})
    return {
        "profile_ref": profile_ref,
        "synthetic_or_deidentified": True,
        "reviewed": True,
        "summary": source["summary"],
        "skills": source["skills"],
        "evidence_items": evidence,
        "experience_years": source["experience_years"],
        "education_summary": source["education_summary"],
        "date_evidence_status": "current",
        "current_location": "Toronto, Ontario, Canada",
        "authorized_work_locations": ["Canada"],
        "requires_sponsorship": False,
        **profile_fields,
    }


def _preferences(profile_ref: str, group: str, target_levels: list[str]) -> dict[str, object]:
    families = {
        "04": ["robotics", "autonomous_systems"],
        "05": ["embedded_systems", "firmware"],
        "06": ["hardware_systems_integration", "controls", "mechatronics", "testing", "verification"],
    }[group]
    titles = {
        "04": ["Robotics Software Engineer", "Autonomy Engineer", "Localization Engineer"],
        "05": ["Firmware Engineer", "Embedded Systems Engineer", "Embedded Test Engineer"],
        "06": ["Systems Integration Engineer", "Controls Engineer", "Verification Engineer"],
    }[group]
    return {
        "confirmed": True,
        "role_families": families,
        "target_titles": titles,
        "target_levels": target_levels,
        "locations": ["Toronto, Ontario, Canada", "Ontario, Canada"],
        "work_arrangements": ["hybrid", "onsite", "remote"],
        "work_authorization_status": "confirmed",
        "selected_exploration_sectors": ["industrial technology", "connected devices"],
        "preferred_companies": [],
        "candidate_current_location": "Toronto, Ontario, Canada",
        "authorized_work_locations": ["Canada"],
        "requires_sponsorship": False,
    }


def _fact(case_id: str, kind: str, slug: str, statement: str) -> dict[str, str]:
    return {"fact_id": f"posting:calibration-{case_id:03d}:{kind}:{slug}", "kind": kind, "statement": statement}


def _ref(case, ref: str) -> dict[str, object]:
    if ref.startswith("profile:"):
        item = next((item for item in case["profile"]["evidence_items"] if item["evidence_id"] == ref), None)
        if item is not None:
            return {"reference": ref, "provenance": item["provenance"], "statement": item["statement"], "evidence_quality": item["evidence_quality"]}
        profile_ref = case["profile"]["profile_ref"]
        profile_facts = {
            f"profile:{profile_ref}:experience-years": ("reviewed-profile-duration", f"The reviewed profile records {case['profile']['experience_years']} years of experience."),
            f"profile:{profile_ref}:education": ("reviewed-profile-education", case["profile"]["education_summary"]),
            f"profile:{profile_ref}:professional-license-status": ("reviewed-profile-license", f"Professional-license status: {case['profile'].get('professional_license_status', 'unknown')}."),
            f"profile:{profile_ref}:clearance-status": ("reviewed-profile-clearance", f"Clearance status: {case['profile'].get('clearance_status', 'unknown')}."),
        }
        provenance, statement = profile_facts[ref]
        return {"reference": ref, "provenance": provenance, "statement": statement, "evidence_quality": "verified"}
    fact = next(fact for fact in case["posting"]["posting_facts"] if fact["fact_id"] == ref)
    return {"reference": ref, "provenance": f"reviewed-posting-{case['case_id']}", "statement": fact["statement"], "evidence_quality": None}


def _make_case(spec: tuple) -> dict[str, object]:
    group, number, title, company, team, location, arrangement, level, category, grade, eligibility, provisional, tags, focus, responsibilities, critical, required, preferred, missing, context = spec
    case_id = f"calibration-{number:03d}"
    profile_ref = f"cal-profile-{group}"
    profile = _profile(profile_ref)
    preferences = _preferences(profile_ref, group, ["junior", "mid", "senior"])
    posting_facts = []
    posting_responsibilities = []
    for slug, text in responsibilities:
        posting_responsibilities.append(text)
        posting_facts.append(_fact(number, "responsibility", slug, text))
    records: dict[str, tuple[dict[str, str], list[str], str]] = {}
    for kind, items in (("critical", critical), ("required", required), ("preferred", preferred)):
        for slug, text, refs in items:
            fact = _fact(number, f"{kind}_requirement" if kind == "critical" else f"{kind}_qualification", slug, text)
            posting_facts.append(fact)
            refs = [f"profile:{profile_ref}:{ref}" for ref in refs]
            records[fact["fact_id"]] = (fact, refs, kind)
    metadata = {
        "location": _fact(number, "location", "work-location", f"The primary work location is {location}."),
        "authorization": _fact(number, "authorization", "authorization-policy", AUTHORIZATION_STATEMENTS[number]),
        "level": _fact(number, "level", "posting-level", "The posting level is unknown and not stated." if level == "unknown" else f"The role is advertised at the {level} level."),
        "posting_date": _fact(number, "posting_date", "posting-date", "The posting date is not stated." if provisional else f"The posting was published on {POSTING_DATES[number]}"),
        "employment_type": _fact(number, "employment_type", "employment-type", "The position is full-time employment."),
    }
    posting_facts.extend(metadata.values())
    critical_text = [item[1] for item in critical]
    required_text = [item[1] for item in required]
    preferred_text = [item[1] for item in preferred]
    description = DESCRIPTION_COPY[number]
    posting = {
        "normalized_id": f"normalized-{case_id}",
        "title": title,
        "company": company,
        "description": description,
        "location": location,
        "work_arrangement": arrangement,
        "employment_type": "full_time",
        "posted_date": None if provisional else metadata["posting_date"]["statement"].split()[-1].rstrip("."),
        "responsibilities": posting_responsibilities,
        "requirements_text": [f"Critical: {text}" for text in critical_text] + [f"Required: {text}" for text in required_text] + [f"Preferred: {text}" for text in preferred_text],
        "posting_sponsorship_available": None if number in {40, 50, 60} else number not in {36, 48},
        "enrollment_requirement": None,
        "graduation_window": None,
        "posting_level": level,
        "posting_facts": posting_facts,
    }
    case: dict[str, object] = {"case_id": case_id, "scenario_id": f"calibration-group-{group}", "split": "calibration", "scenario_category": category, "ranking_group": f"calibration-group-{group}", "stage": "A", "proposal_status": "proposed", "profile": profile, "preferences": preferences, "posting": posting}
    posting_by_slug = {fact["fact_id"].split(":")[-1]: fact["fact_id"] for fact in posting_facts}
    def resolve(token: str) -> str:
        aliases = {
            "@location": metadata["location"]["fact_id"],
            "@authorization": metadata["authorization"]["fact_id"],
            "@level": metadata["level"]["fact_id"],
            "@date": metadata["posting_date"]["fact_id"],
            "@pref_auth": f"preferences:{profile_ref}:work_authorization",
            "@pref_level": f"preferences:{profile_ref}:target_level",
            "@target": f"preferences:{profile_ref}:target_level",
            "@duration": f"profile:{profile_ref}:experience-years",
            "@license": f"profile:{profile_ref}:professional-license-status",
            "@clearance": f"profile:{profile_ref}:clearance-status",
        }
        return aliases.get(token, posting_by_slug.get(token, f"profile:{profile_ref}:{token}"))

    positive_code, positive_statement, positive_tokens = POSITIVE_REASONS[number]
    positive = {"code": positive_code, "statement": positive_statement, "evidence_references": [resolve(token) for token in positive_tokens]}
    gaps = [
        {"code": code, "statement": statement, "evidence_references": list(dict.fromkeys([resolve(fact_slug), *(resolve(token) for token in refs)]))}
        for code, statement, fact_slug, refs in GAP_PLANS.get(number, [])
    ]
    location_ref = metadata["location"]["fact_id"]
    auth_ref = metadata["authorization"]["fact_id"]
    reason_code, reason_statement, reason_tokens = ELIGIBILITY_PLANS[number]
    eligibility_reasons = [{
        "code": reason_code,
        "statement": reason_statement,
        "evidence_references": [resolve(token) for token in reason_tokens],
        "posting_fact": location_ref if reason_code == "eligible_facts" else auth_ref if reason_code in {"hard_authorization_conflict", "hard_clearance_conflict", "eligibility_unknown"} else resolve(reason_tokens[0]),
        "profile_fact": resolve("@pref_auth") if reason_code in {"eligible_facts", "hard_authorization_conflict", "eligibility_unknown"} else resolve(reason_tokens[-1]),
    }]
    important_evidence = [_ref(case, f"profile:{profile_ref}:{ident}") for ident in focus if next(item for item in profile["evidence_items"] if item["evidence_id"] == f"profile:{profile_ref}:{ident}")["evidence_kind"] == "demonstrated"]
    case.update({
        "source": {"provider": "synthetic_ats", "source_id": f"reviewed-{case_id}", "external_job_id": f"deidentified-{case_id}", "source_url": f"https://jobs.example.test/{case_id}", "retrieved_at": "2026-07-23T12:00:00Z", "provider_position": number % 10 or 10, "verification_status": "verified_active"},
        "expected_eligibility": eligibility,
        "proposed_eligibility_reasons": eligibility_reasons,
        "proposed_grade": grade,
        "proposed_provisional": provisional,
        "provisional_reason_codes": ["incomplete_description", "unresolved_authorization", "missing_date", "uncertain_level"] if provisional else [],
        "critical_requirements": [{"requirement_id": fact["fact_id"], "text": fact["statement"], "importance": "critical", "evidence_references": refs, "fact_id": fact["fact_id"]} for fact, refs, kind in records.values() if kind == "critical"],
        "required_qualifications": [{"qualification_id": fact["fact_id"], "text": fact["statement"], "evidence_references": refs, "fact_id": fact["fact_id"]} for fact, refs, kind in records.values() if kind == "required"],
        "preferred_qualifications": [{"qualification_id": fact["fact_id"], "text": fact["statement"], "evidence_references": refs, "fact_id": fact["fact_id"]} for fact, refs, kind in records.values() if kind == "preferred"],
        "important_evidence": important_evidence,
        "evidence_assessment": {"quality": "verified" if important_evidence else "incomplete", "provenance": important_evidence},
        "important_gaps": gaps,
        "proposed_positive_reasons": [positive],
        "proposed_material_gap_reasons": gaps,
        "proposed_reasons": [positive, *gaps],
        "rationale": RATIONALES[number],
        "proposal_confidence": "low" if provisional else "high" if grade == "excellent" else "medium",
        "review_tags": ["deidentified_profile", *tags],
        "review_required": True,
        "apply_worthy": grade != "dont_match" and eligibility != "ineligible",
        "normal_feed_visible": grade != "dont_match" and eligibility != "ineligible",
        "human_ranking_tier": {"excellent": "tier_1", "good": "tier_2", "weak": "tier_3", "dont_match": "not_ranked"}[grade],
        "comparable_pair_annotations": [],
        "reviewer_decision": "",
        "reviewer_notes": "",
        "approval_status": "unapproved",
    })
    return case


PAIR_DECISIONS = {
    frozenset(("calibration-031", "calibration-032")): ("calibration-032", "calibration-032 is preferred to calibration-031 because the vehicle integration role owns package boundaries, frame calibration, and closed-course safety gates, while calibration-031 is narrower runtime ownership."),
    frozenset(("calibration-031", "calibration-033")): ("calibration-033", "calibration-033 is preferred to calibration-031 because map-quality ownership and frame-drift resolution are more specific to localization outcomes than runtime maintenance."),
    frozenset(("calibration-031", "calibration-034")): ("calibration-031 is preferred to calibration-034 because it owns the autonomy runtime and release trials, while calibration-034 owns a narrower perception handoff boundary."),
    frozenset(("calibration-031", "calibration-038")): ("calibration-031 is preferred to calibration-038 because direct runtime release ownership is broader than field incident support after deployment."),
    frozenset(("calibration-032", "calibration-033")): ("calibration-033 is preferred to calibration-032 because localization and mapping are the direct product outcome, while integration covers a wider but less specialized vehicle boundary."),
    frozenset(("calibration-032", "calibration-034")): ("calibration-032 is preferred to calibration-034 because vehicle-wide autonomy integration covers calibration, planning, and safety gates beyond the perception handoff."),
    frozenset(("calibration-032", "calibration-038")): ("calibration-032 is preferred to calibration-038 because it owns package integration and closed-course gates, while calibration-038 emphasizes incident support."),
    frozenset(("calibration-033", "calibration-034")): ("calibration-033 is preferred to calibration-034 because map regression ownership is closer to the profile's localization evidence than perception interface delivery."),
    frozenset(("calibration-033", "calibration-038")): ("calibration-033 is preferred to calibration-038 because mapping ownership and frame-calibration responsibility are more central than operational fleet reliability support."),
    frozenset(("calibration-034", "calibration-038")): ("calibration-038", "calibration-038 is preferred to calibration-034 because field robotics reliability ownership is a stronger substantive grade, while calibration-034 has a limited runtime-performance depth gap."),
    frozenset(("calibration-031", "calibration-040")): ("calibration-031 is preferred to calibration-040 because it provides a confirmed level, date, and authorization context in addition to the shared robotics integration evidence."),
    frozenset(("calibration-032", "calibration-040")): ("calibration-032 is preferred to calibration-040 because the complete vehicle integration posting has confirmed eligibility facts while calibration-040 remains unresolved."),
    frozenset(("calibration-033", "calibration-040")): ("calibration-033 is preferred to calibration-040 because map-quality ownership is fully specified and eligible, whereas calibration-040 omits material posting metadata."),
    frozenset(("calibration-034", "calibration-040")): ("calibration-034 is preferred to calibration-040 because its direct perception handoff core is eligible and the runtime-performance gap is limited, while calibration-040 has a material actuator-controls stretch and provisional eligibility."),
    frozenset(("calibration-038", "calibration-040")): ("calibration-038 is preferred to calibration-040 because fleet reliability responsibilities and eligibility are confirmed, while calibration-040 has unresolved level and authorization facts."),
    frozenset(("calibration-041", "calibration-042")): ("calibration-041 is preferred to calibration-042 because it combines driver ownership with RTOS scheduling and board commissioning, while calibration-042 centers on the driver boundary."),
    frozenset(("calibration-041", "calibration-043")): ("calibration-043 is preferred to calibration-041 because constrained real-time scheduling ownership and recovery responsibility are the sharper match for the timing-controller target."),
    frozenset(("calibration-041", "calibration-045")): ("calibration-041 is preferred to calibration-045 because direct firmware and driver ownership is closer to the embedded target than release validation ownership."),
    frozenset(("calibration-042", "calibration-043")): ("calibration-043 is preferred to calibration-042 because real-time scheduling and constrained-resource ownership are more central than board-support delivery."),
    frozenset(("calibration-042", "calibration-045")): ("calibration-045", "calibration-045 is preferred to calibration-042 because firmware release validation is an Excellent match, while calibration-042 has a limited interrupt/DMA depth gap despite its direct driver work."),
    frozenset(("calibration-043", "calibration-045")): ("calibration-043 is preferred to calibration-045 because timing, memory, and recovery implementation is broader product ownership than release regression."),
    frozenset(("calibration-041", "calibration-050")): ("calibration-041 is preferred to calibration-050 because its firmware lifecycle is fully specified and eligible, while calibration-050 has unknown posting authority and insufficient automation depth."),
    frozenset(("calibration-042", "calibration-050")): ("calibration-042 is preferred to calibration-050 because driver and board-support ownership is confirmed, while calibration-050 remains provisional with unresolved posting metadata."),
    frozenset(("calibration-043", "calibration-050")): ("calibration-043 is preferred to calibration-050 because direct real-time firmware ownership exceeds the incomplete test assignment and its unresolved eligibility."),
    frozenset(("calibration-045", "calibration-050")): ("calibration-045 is preferred to calibration-050 because release-validation ownership is demonstrated at full scope, while Python automation depth and eligibility remain unresolved for calibration-050."),
    frozenset(("calibration-051", "calibration-052")): ("calibration-051 is preferred to calibration-052 because end-to-end sensor, actuator, and interface integration is broader than regulated verification planning."),
    frozenset(("calibration-051", "calibration-053")): ("calibration-051 is preferred to calibration-053 because it owns the integrated product boundary, while calibration-053 focuses on controls-only validation."),
    frozenset(("calibration-051", "calibration-054")): ("calibration-051 is preferred to calibration-054 because release integration and traceability span the product lifecycle beyond prototype bring-up."),
    frozenset(("calibration-052", "calibration-053")): ("calibration-053", "calibration-053 is preferred to calibration-052 because controls validation is an Excellent match, while calibration-052 has a limited medical-device design-control depth gap."),
    frozenset(("calibration-052", "calibration-054")): ("calibration-054", "calibration-054 is preferred to calibration-052 because prototype bring-up is an Excellent match, while calibration-052 has a limited medical-device design-control depth gap."),
    frozenset(("calibration-053", "calibration-054")): ("calibration-053 is preferred to calibration-054 because control-loop and hardware-in-loop acceptance decisions are deeper validation ownership than early prototype integration."),
    frozenset(("calibration-051", "calibration-060")): ("calibration-051 is preferred to calibration-060 because its system-integration scope and eligibility are fully specified, while calibration-060 is provisional."),
    frozenset(("calibration-052", "calibration-060")): ("calibration-052 is preferred to calibration-060 because regulated verification planning is fully specified and eligible, while calibration-060 leaves level and authorization unresolved."),
    frozenset(("calibration-053", "calibration-060")): ("calibration-053 is preferred to calibration-060 because controls validation responsibilities and eligibility are confirmed, while calibration-060 has an abbreviated posting."),
    frozenset(("calibration-054", "calibration-060")): ("calibration-054 is preferred to calibration-060 because hardware bring-up and cross-team handoff are fully specified and eligible, while calibration-060 remains provisional."),
}


def _add_pairs(cases: list[dict[str, object]]) -> None:
    grade_rank = {"excellent": 3, "good": 2, "weak": 1, "dont_match": 0}
    tier_rank = {"tier_1": 3, "tier_2": 2, "tier_3": 1, "not_ranked": 0}
    eligibility_rank = {"eligible": 1, "unknown": 0, "ineligible": -1}
    visible = [case for case in cases if case["normal_feed_visible"]]
    for index, left in enumerate(visible):
        for right in visible[index + 1 :]:
            left_key = (grade_rank[left["proposed_grade"]], tier_rank[left["human_ranking_tier"]], eligibility_rank[left["expected_eligibility"]])
            right_key = (grade_rank[right["proposed_grade"]], tier_rank[right["human_ranking_tier"]], eligibility_rank[right["expected_eligibility"]])
            decision = PAIR_DECISIONS[frozenset((left["case_id"], right["case_id"]))]
            if isinstance(decision, str):
                preferred_id = decision.split(" ", 1)[0]
                rationale = decision
            else:
                preferred_id, rationale = decision
            preferred = left if left["case_id"] == preferred_id else right
            other = right if preferred is left else left
            expected_preferred = left if left_key > right_key else right
            if left_key == right_key:
                assert preferred["case_id"] == preferred_id
            else:
                assert preferred["case_id"] == expected_preferred["case_id"]
            preferred["comparable_pair_annotations"].append({"other_case_id": other["case_id"], "relationship": "preferred_to_other", "rationale": rationale})


def build() -> None:
    calibration_path = ROOT / "calibration.json"
    manifest_path = ROOT / "manifest.json"
    raw_calibration = calibration_path.read_text(encoding="utf-8")
    generated = [_make_case(spec) for spec in CASES]
    for group in ("04", "05", "06"):
        _add_pairs([case for case in generated if case["ranking_group"] == f"calibration-group-{group}"])
    marker = '  {\n    "case_id": "calibration-031"'
    marker_index = raw_calibration.index(marker)
    raw_prefix = raw_calibration[:marker_index].rstrip()
    inherited = _repair_inherited_metadata(json.loads(raw_prefix.rstrip(",") + "]"))
    existing = json.loads(raw_calibration)
    assert generated == existing[30:], "unexpected change outside inherited metadata repair"
    inherited_json = json.dumps(inherited, ensure_ascii=False, indent=2).rstrip()
    calibration_path.write_text(inherited_json[:-1] + ",\n" + raw_calibration[marker_index:].rstrip() + "\n", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["splits"]["calibration"]["sha256"] = hashlib.sha256(calibration_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
