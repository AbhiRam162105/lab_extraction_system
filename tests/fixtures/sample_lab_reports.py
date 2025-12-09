"""
Sample lab report data for testing.
"""

# Sample Gemini extraction response
SAMPLE_EXTRACTION_RESPONSE = {
    "patient_info": {
        "patient_name": "John Doe",
        "patient_id": "P12345",
        "age": "45 years",
        "gender": "Male",
        "sample_date": "2024-01-15"
    },
    "lab_results": [
        {
            "test_name": "Hemoglobin",
            "value": "14.5",
            "unit": "g/dL",
            "reference_range": "13.0 - 17.0",
            "flag": ""
        },
        {
            "test_name": "White Blood Cells",
            "value": "8500",
            "unit": "/uL",
            "reference_range": "4000 - 11000",
            "flag": ""
        },
        {
            "test_name": "Red Blood Cells",
            "value": "5.2",
            "unit": "million/uL",
            "reference_range": "4.5 - 5.5",
            "flag": ""
        },
        {
            "test_name": "Platelet Count",
            "value": "250000",
            "unit": "/uL",
            "reference_range": "150000 - 400000",
            "flag": ""
        },
        {
            "test_name": "Creatinine",
            "value": "1.8",
            "unit": "mg/dL",
            "reference_range": "0.7 - 1.3",
            "flag": "H"
        }
    ]
}

# Sample raw rows for normalizer testing
SAMPLE_RAW_ROWS = [
    {"test_name": "Hemoglobin", "value": "14.5", "unit": "g/dL", "reference_range": "13.0 - 17.0", "flag": ""},
    {"test_name": "WBC", "value": "8500", "unit": "/uL", "reference_range": "4000 - 11000", "flag": ""},
    {"test_name": "RBC", "value": "5.2", "unit": "million/uL", "reference_range": "4.5 - 5.5", "flag": ""},
    {"test_name": "Creatinine", "value": "1.8", "unit": "mg/dL", "reference_range": "0.7 - 1.3", "flag": "HIGH"},
]

# Sample normalized results (expected output)
SAMPLE_NORMALIZED_RESULTS = [
    {
        "test_name": "Hemoglobin",
        "original_name": "Hemoglobin",
        "value": "14.5",
        "value_numeric": 14.5,
        "unit": "g/dL",
        "reference_range": "13.0 - 17.0",
        "ref_low": 13.0,
        "ref_high": 17.0,
        "flag": "",
        "loinc_code": "718-7",
        "category": "Hematology",
        "mapping_method": "exact"
    },
    {
        "test_name": "White Blood Cell Count",
        "original_name": "WBC",
        "value": "8500",
        "value_numeric": 8500.0,
        "unit": "/uL",
        "reference_range": "4000 - 11000",
        "ref_low": 4000.0,
        "ref_high": 11000.0,
        "flag": "",
        "loinc_code": "6690-2",
        "category": "Hematology",
        "mapping_method": "alias"
    }
]

# Test mappings subset
SAMPLE_TEST_MAPPINGS = {
    "version": "1.0",
    "mappings": {
        "hemoglobin": {
            "canonical_name": "Hemoglobin",
            "loinc_code": "718-7",
            "category": "Hematology",
            "unit": "g/dL",
            "aliases": ["hb", "hgb", "haemoglobin", "hemoglobin level"]
        },
        "white_blood_cells": {
            "canonical_name": "White Blood Cell Count",
            "loinc_code": "6690-2",
            "category": "Hematology",
            "unit": "/uL",
            "aliases": ["wbc", "wbc count", "leukocytes", "total wbc"]
        },
        "red_blood_cells": {
            "canonical_name": "Red Blood Cell Count",
            "loinc_code": "789-8",
            "category": "Hematology",
            "unit": "million/uL",
            "aliases": ["rbc", "rbc count", "erythrocytes"]
        },
        "rdw": {
            "canonical_name": "Red Cell Distribution Width",
            "loinc_code": "788-0",
            "category": "Hematology",
            "unit": "%",
            "aliases": ["rdw", "rdw-cv", "rbc distribution width"]
        },
        "creatinine": {
            "canonical_name": "Creatinine",
            "loinc_code": "2160-0",
            "category": "Renal Panel",
            "unit": "mg/dL",
            "aliases": ["creatinine", "creat", "serum creatinine"]
        },
        "platelets": {
            "canonical_name": "Platelet Count",
            "loinc_code": "777-3",
            "category": "Hematology",
            "unit": "/uL",
            "aliases": ["plt", "platelets", "platelet count", "thrombocytes"]
        }
    }
}

# Quality metrics for a good image
GOOD_IMAGE_METRICS = {
    "blur_score": 150.0,
    "contrast_score": 0.85,
    "brightness": 180.0,
    "text_clarity": 0.75,
    "noise_level": 0.05,
    "text_density": 0.15
}

# Quality metrics for a poor image
POOR_IMAGE_METRICS = {
    "blur_score": 25.0,
    "contrast_score": 0.3,
    "brightness": 90.0,
    "text_clarity": 0.2,
    "noise_level": 0.4,
    "text_density": 0.02
}
