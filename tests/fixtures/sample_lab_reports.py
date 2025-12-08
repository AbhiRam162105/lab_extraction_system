"""
Sample lab report data fixtures for testing.
Generates realistic test data without calling external APIs.
"""
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class TestValue:
    """Represents a single test value."""
    name: str
    value: str
    unit: str
    reference_range: str
    status: str = "normal"
    standardized_name: Optional[str] = None


@dataclass
class PatientInfo:
    """Patient information."""
    name: str
    age: int
    gender: str
    patient_id: str


@dataclass
class LabReportSample:
    """Complete lab report sample."""
    patient: PatientInfo
    tests: List[TestValue]
    lab_name: str = "Sample Laboratory"
    report_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    sample_date: str = field(default_factory=lambda: (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))
    confidence: float = 0.95


# =============================================================================
# Hematology Panel Data
# =============================================================================

def generate_hematology_panel(abnormal: bool = False) -> List[TestValue]:
    """Generate complete blood count / hematology panel data."""
    
    if abnormal:
        # Generate some abnormal values
        return [
            TestValue("Hemoglobin", "10.5", "g/dL", "13.5-17.5", "low"),
            TestValue("Hematocrit", "32", "%", "40-52", "low"),
            TestValue("Red Blood Cells", "3.8", "million/μL", "4.5-5.5", "low"),
            TestValue("White Blood Cells", "15000", "/μL", "4000-11000", "high"),
            TestValue("Platelet Count", "450000", "/μL", "150000-400000", "high"),
            TestValue("Mean Corpuscular Volume", "78", "fL", "80-100", "low"),
            TestValue("Mean Corpuscular Hemoglobin", "27", "pg", "27-33", "normal"),
            TestValue("Mean Corpuscular Hemoglobin Concentration", "33", "g/dL", "32-36", "normal"),
            TestValue("Red Cell Distribution Width", "16", "%", "11.5-14.5", "high"),
            TestValue("Neutrophils", "75", "%", "40-70", "high"),
            TestValue("Lymphocytes", "15", "%", "20-40", "low"),
            TestValue("Monocytes", "6", "%", "2-8", "normal"),
            TestValue("Eosinophils", "3", "%", "1-4", "normal"),
            TestValue("Basophils", "1", "%", "0-1", "normal"),
        ]
    else:
        return [
            TestValue("Hemoglobin", "14.5", "g/dL", "13.5-17.5", "normal"),
            TestValue("Hematocrit", "43", "%", "40-52", "normal"),
            TestValue("Red Blood Cells", "4.8", "million/μL", "4.5-5.5", "normal"),
            TestValue("White Blood Cells", "7500", "/μL", "4000-11000", "normal"),
            TestValue("Platelet Count", "250000", "/μL", "150000-400000", "normal"),
            TestValue("Mean Corpuscular Volume", "88", "fL", "80-100", "normal"),
            TestValue("Mean Corpuscular Hemoglobin", "30", "pg", "27-33", "normal"),
            TestValue("Mean Corpuscular Hemoglobin Concentration", "34", "g/dL", "32-36", "normal"),
            TestValue("Red Cell Distribution Width", "13", "%", "11.5-14.5", "normal"),
            TestValue("Neutrophils", "55", "%", "40-70", "normal"),
            TestValue("Lymphocytes", "35", "%", "20-40", "normal"),
            TestValue("Monocytes", "5", "%", "2-8", "normal"),
            TestValue("Eosinophils", "3", "%", "1-4", "normal"),
            TestValue("Basophils", "0.5", "%", "0-1", "normal"),
        ]


# =============================================================================
# Metabolic Panel Data
# =============================================================================

def generate_metabolic_panel(abnormal: bool = False) -> List[TestValue]:
    """Generate comprehensive metabolic panel data."""
    
    if abnormal:
        return [
            TestValue("Blood Glucose Fasting", "185", "mg/dL", "70-100", "high"),
            TestValue("Blood Urea Nitrogen", "35", "mg/dL", "7-20", "high"),
            TestValue("Creatinine", "2.5", "mg/dL", "0.7-1.3", "high"),
            TestValue("Sodium", "148", "mEq/L", "136-145", "high"),
            TestValue("Potassium", "5.8", "mEq/L", "3.5-5.0", "high"),
            TestValue("Chloride", "108", "mEq/L", "98-106", "high"),
            TestValue("Carbon Dioxide", "20", "mEq/L", "23-29", "low"),
            TestValue("Calcium", "11.5", "mg/dL", "8.5-10.5", "high"),
            TestValue("Total Protein", "5.8", "g/dL", "6.0-8.3", "low"),
            TestValue("Albumin", "2.8", "g/dL", "3.5-5.0", "low"),
            TestValue("Bilirubin Total", "2.5", "mg/dL", "0.1-1.2", "high"),
            TestValue("Alkaline Phosphatase", "180", "U/L", "44-147", "high"),
            TestValue("AST (SGOT)", "85", "U/L", "10-40", "high"),
            TestValue("ALT (SGPT)", "95", "U/L", "7-56", "high"),
        ]
    else:
        return [
            TestValue("Blood Glucose Fasting", "92", "mg/dL", "70-100", "normal"),
            TestValue("Blood Urea Nitrogen", "15", "mg/dL", "7-20", "normal"),
            TestValue("Creatinine", "1.0", "mg/dL", "0.7-1.3", "normal"),
            TestValue("Sodium", "140", "mEq/L", "136-145", "normal"),
            TestValue("Potassium", "4.2", "mEq/L", "3.5-5.0", "normal"),
            TestValue("Chloride", "102", "mEq/L", "98-106", "normal"),
            TestValue("Carbon Dioxide", "25", "mEq/L", "23-29", "normal"),
            TestValue("Calcium", "9.5", "mg/dL", "8.5-10.5", "normal"),
            TestValue("Total Protein", "7.2", "g/dL", "6.0-8.3", "normal"),
            TestValue("Albumin", "4.2", "g/dL", "3.5-5.0", "normal"),
            TestValue("Bilirubin Total", "0.8", "mg/dL", "0.1-1.2", "normal"),
            TestValue("Alkaline Phosphatase", "75", "U/L", "44-147", "normal"),
            TestValue("AST (SGOT)", "28", "U/L", "10-40", "normal"),
            TestValue("ALT (SGPT)", "32", "U/L", "7-56", "normal"),
        ]


# =============================================================================
# Lipid Panel Data
# =============================================================================

def generate_lipid_panel(abnormal: bool = False) -> List[TestValue]:
    """Generate lipid panel data."""
    
    if abnormal:
        return [
            TestValue("Total Cholesterol", "285", "mg/dL", "<200", "high"),
            TestValue("LDL Cholesterol", "180", "mg/dL", "<100", "high"),
            TestValue("HDL Cholesterol", "32", "mg/dL", ">40", "low"),
            TestValue("Triglycerides", "350", "mg/dL", "<150", "high"),
            TestValue("VLDL Cholesterol", "70", "mg/dL", "5-40", "high"),
        ]
    else:
        return [
            TestValue("Total Cholesterol", "185", "mg/dL", "<200", "normal"),
            TestValue("LDL Cholesterol", "95", "mg/dL", "<100", "normal"),
            TestValue("HDL Cholesterol", "55", "mg/dL", ">40", "normal"),
            TestValue("Triglycerides", "120", "mg/dL", "<150", "normal"),
            TestValue("VLDL Cholesterol", "24", "mg/dL", "5-40", "normal"),
        ]


# =============================================================================
# Thyroid Panel Data
# =============================================================================

def generate_thyroid_panel(abnormal: bool = False) -> List[TestValue]:
    """Generate thyroid function panel data."""
    
    if abnormal:
        return [
            TestValue("TSH", "0.2", "μIU/mL", "0.4-4.0", "low"),
            TestValue("Free T4", "3.5", "ng/dL", "0.8-1.8", "high"),
            TestValue("Free T3", "8.5", "pg/mL", "2.3-4.2", "high"),
            TestValue("Total T4", "18.0", "μg/dL", "4.5-12.0", "high"),
            TestValue("Total T3", "280", "ng/dL", "80-200", "high"),
        ]
    else:
        return [
            TestValue("TSH", "2.5", "μIU/mL", "0.4-4.0", "normal"),
            TestValue("Free T4", "1.2", "ng/dL", "0.8-1.8", "normal"),
            TestValue("Free T3", "3.2", "pg/mL", "2.3-4.2", "normal"),
            TestValue("Total T4", "8.0", "μg/dL", "4.5-12.0", "normal"),
            TestValue("Total T3", "150", "ng/dL", "80-200", "normal"),
        ]


# =============================================================================
# Sample Patients
# =============================================================================

SAMPLE_PATIENTS = [
    PatientInfo("John Doe", 45, "Male", "P12345"),
    PatientInfo("Jane Smith", 32, "Female", "P12346"),
    PatientInfo("Robert Johnson", 58, "Male", "P12347"),
    PatientInfo("Mary Williams", 41, "Female", "P12348"),
    PatientInfo("James Brown", 67, "Male", "P12349"),
    PatientInfo("Patricia Davis", 29, "Female", "P12350"),
    PatientInfo("Michael Miller", 52, "Male", "P12351"),
    PatientInfo("Linda Wilson", 38, "Female", "P12352"),
]


# =============================================================================
# Report Generators
# =============================================================================

def generate_random_report(include_abnormal: bool = False) -> LabReportSample:
    """Generate a random complete lab report."""
    patient = random.choice(SAMPLE_PATIENTS)
    
    # Randomly select panels
    tests = []
    tests.extend(generate_hematology_panel(include_abnormal and random.random() > 0.5))
    
    if random.random() > 0.3:
        tests.extend(generate_metabolic_panel(include_abnormal and random.random() > 0.5))
    
    if random.random() > 0.5:
        tests.extend(generate_lipid_panel(include_abnormal and random.random() > 0.5))
    
    if random.random() > 0.7:
        tests.extend(generate_thyroid_panel(include_abnormal and random.random() > 0.5))
    
    return LabReportSample(
        patient=patient,
        tests=tests,
        confidence=random.uniform(0.85, 0.99)
    )


def generate_flagged_report() -> LabReportSample:
    """Generate a report that should be flagged for review."""
    patient = random.choice(SAMPLE_PATIENTS)
    
    # Mostly abnormal values
    tests = []
    tests.extend(generate_hematology_panel(abnormal=True))
    tests.extend(generate_metabolic_panel(abnormal=True))
    
    return LabReportSample(
        patient=patient,
        tests=tests,
        confidence=0.65  # Low confidence
    )


def generate_difficult_report() -> Dict[str, Any]:
    """Generate a report with difficult-to-read test names."""
    return {
        "patient_info": {
            "name": "Test Patient",
            "age": 40,
            "gender": "Male",
            "patient_id": "P99999"
        },
        "tests": [
            {"name": "Hb", "value": "14.5", "unit": "g/dL", "reference_range": "13.5-17.5"},
            {"name": "WBC Count", "value": "7500", "unit": "/mcL", "reference_range": "4000-11000"},
            {"name": "RBC", "value": "4.8", "unit": "M/uL", "reference_range": "4.5-5.5"},
            {"name": "PLT", "value": "250", "unit": "K/uL", "reference_range": "150-400"},
            {"name": "FBS", "value": "92", "unit": "mg/dl", "reference_range": "70-100"},
            {"name": "S. Creatinine", "value": "1.0", "unit": "mg/dL", "reference_range": "0.7-1.3"},
            {"name": "SGPT", "value": "32", "unit": "IU/L", "reference_range": "7-56"},
            {"name": "SGOT", "value": "28", "unit": "IU/L", "reference_range": "10-40"},
        ],
        "confidence": 0.75
    }


def to_dict(report: LabReportSample) -> Dict[str, Any]:
    """Convert LabReportSample to dictionary."""
    return {
        "patient_info": {
            "name": report.patient.name,
            "age": report.patient.age,
            "gender": report.patient.gender,
            "patient_id": report.patient.patient_id
        },
        "lab_info": {
            "lab_name": report.lab_name,
            "report_date": report.report_date,
            "sample_date": report.sample_date
        },
        "tests": [
            {
                "name": t.name,
                "value": t.value,
                "unit": t.unit,
                "reference_range": t.reference_range,
                "status": t.status,
                "standardized_name": t.standardized_name
            }
            for t in report.tests
        ],
        "confidence": report.confidence
    }


# =============================================================================
# Test Fixtures
# =============================================================================

def get_sample_reports(count: int = 5, include_abnormal: bool = True) -> List[Dict[str, Any]]:
    """Get multiple sample reports for testing."""
    return [to_dict(generate_random_report(include_abnormal)) for _ in range(count)]


def get_edge_case_reports() -> List[Dict[str, Any]]:
    """Get reports covering edge cases."""
    return [
        # Empty tests list
        {
            "patient_info": {"name": "Empty Test", "age": 30},
            "tests": [],
            "confidence": 0.0
        },
        # Very long test name
        {
            "patient_info": {"name": "Long Names", "age": 35},
            "tests": [
                {"name": "Complete Blood Count with Differential and Platelet Count", 
                 "value": "See detailed report", "unit": "", "reference_range": "N/A"}
            ],
            "confidence": 0.85
        },
        # Unusual units
        {
            "patient_info": {"name": "Unusual Units", "age": 40},
            "tests": [
                {"name": "Hemoglobin", "value": "145", "unit": "g/L", "reference_range": "135-175"},
                {"name": "Glucose", "value": "5.1", "unit": "mmol/L", "reference_range": "3.9-5.6"}
            ],
            "confidence": 0.90
        },
        # Difficult values
        generate_difficult_report()
    ]
