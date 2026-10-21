"""Realistic openFDA drug label response fixtures for testing."""

LIPITOR_V1_RAW = {
    "id": "spl-id-lipitor-v1",
    "set_id": "spl-set-lipitor-001",
    "version": "1",
    "effective_time": "20210115",
    "openfda": {
        "brand_name": ["LIPITOR"],
        "generic_name": ["ATORVASTATIN CALCIUM"],
        "substance_name": ["ATORVASTATIN"],
        "manufacturer_name": ["Pfizer Laboratories Div Pfizer Inc"],
        "spl_set_id": ["spl-set-lipitor-001"],
        "spl_id": ["spl-id-lipitor-v1"],
        "application_number": ["NDA020702"],
    },
    "indications_and_usage": [
        "LIPITOR is indicated to reduce the risk of myocardial infarction in adult patients with coronary heart disease."
    ],
    "warnings_and_precautions": [
        "Myopathy and Rhabdomyolysis: Rare cases of rhabdomyolysis with acute renal failure secondary to myoglobinuria have been reported."
    ],
    "contraindications": [
        "Active liver disease, which may include unexplained persistent elevations in hepatic transaminase levels."
    ],
}

LIPITOR_V2_RAW = {
    "id": "spl-id-lipitor-v2",
    "set_id": "spl-set-lipitor-001",
    "version": "2",
    "effective_time": "20220610",
    "openfda": {
        "brand_name": ["LIPITOR"],
        "generic_name": ["ATORVASTATIN CALCIUM"],
        "substance_name": ["ATORVASTATIN"],
        "manufacturer_name": ["Pfizer Laboratories Div Pfizer Inc"],
        "spl_set_id": ["spl-set-lipitor-001"],
        "spl_id": ["spl-id-lipitor-v2"],
        "application_number": ["NDA020702"],
    },
    "boxed_warning": [
        "WARNING: RISK OF IMMUNE-MEDIATED NECROTIZING MYOPATHY\n"
        "There have been rare reports of immune-mediated necrotizing myopathy (IMNM), "
        "an autoimmune myopathy, associated with statin use."
    ],
    "indications_and_usage": [
        "LIPITOR is indicated to reduce the risk of myocardial infarction, stroke, "
        "and revascularization procedures in adult patients."
    ],
    "warnings_and_precautions": [
        "Myopathy and Rhabdomyolysis: Rare cases of rhabdomyolysis with acute renal failure have been reported.\n"
        "Discontinue LIPITOR if markedly elevated CK levels occur or myopathy is diagnosed.",
        "Immune-Mediated Necrotizing Myopathy (IMNM): Discontinue LIPITOR if IMNM is suspected.",
    ],
    "contraindications": [
        "Active liver disease, which may include unexplained persistent elevations in hepatic transaminase levels."
    ],
}

LIPITOR_V3_RAW = {
    "id": "spl-id-lipitor-v3",
    "set_id": "spl-set-lipitor-001",
    "version": "3",
    "effective_time": "20231120",
    "openfda": {
        "brand_name": ["LIPITOR"],
        "generic_name": ["ATORVASTATIN CALCIUM"],
        "substance_name": ["ATORVASTATIN"],
        "manufacturer_name": ["Pfizer Laboratories Div Pfizer Inc"],
        "spl_set_id": ["spl-set-lipitor-001"],
        "spl_id": ["spl-id-lipitor-v3"],
        "application_number": ["NDA020702"],
    },
    "boxed_warning": [
        "WARNING: RISK OF IMMUNE-MEDIATED NECROTIZING MYOPATHY\n"
        "There have been rare reports of immune-mediated necrotizing myopathy (IMNM), "
        "an autoimmune myopathy, associated with statin use."
    ],
    "indications_and_usage": [
        "LIPITOR is indicated to reduce the risk of myocardial infarction, stroke, "
        "and revascularization procedures in adult patients."
    ],
    "warnings_and_precautions": [
        "Myopathy and Rhabdomyolysis: Discontinue LIPITOR if markedly elevated CK levels occur.",
        "Immune-Mediated Necrotizing Myopathy (IMNM): Discontinue LIPITOR if IMNM is suspected.",
        "Increases in HbA1c and fasting serum glucose levels have been reported with statins.",
    ],
    "contraindications": [
        "Hypersensitivity to any component of this medication.",
        "Active liver disease.",
    ],
}

MOCK_OPENFDA_LIPITOR_RESPONSE = {
    "meta": {
        "disclaimer": "Do not rely on openFDA to make decisions regarding medical care.",
        "terms": "https://open.fda.gov/terms/",
        "license": "https://open.fda.gov/license/",
        "last_updated": "2024-01-01",
        "results": {"skip": 0, "limit": 20, "total": 3},
    },
    "results": [
        LIPITOR_V1_RAW,
        LIPITOR_V2_RAW,
        LIPITOR_V3_RAW,
    ],
}
