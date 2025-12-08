from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlmodel import Field, SQLModel, Column, JSON, Relationship


class Document(SQLModel, table=True):
    """Document record for uploaded lab reports."""
    id: Optional[str] = Field(default=None, primary_key=True)
    filename: str
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending")  # pending, processing, completed, failed
    file_path: str
    content_type: str


class ExtractionResult(SQLModel, table=True):
    """Raw extraction result from Gemini Vision API."""
    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: str = Field(foreign_key="document.id", index=True)
    extracted_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    confidence_score: float = 0.0
    needs_review: bool = Field(default=False)
    review_reason: Optional[str] = Field(default=None)
    
    # Processing timing (in seconds)
    preprocessing_time: Optional[float] = Field(default=None)  # Image preprocessing
    pass1_time: Optional[float] = Field(default=None)  # Vision extraction
    pass2_time: Optional[float] = Field(default=None)  # Structure + validation
    pass3_time: Optional[float] = Field(default=None)  # Standardization
    total_time: Optional[float] = Field(default=None)  # Total processing time
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StandardizedTestDefinition(SQLModel, table=True):
    """
    Master table of standardized test definitions.
    
    Loaded from test_mappings.yaml and used for normalizing test names
    across different lab reports.
    """
    __tablename__ = "standardized_test_definition"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    test_key: str = Field(unique=True, index=True)  # e.g., "hemoglobin"
    canonical_name: str = Field(index=True)  # e.g., "Hemoglobin"
    loinc_code: Optional[str] = Field(default=None, index=True)
    category: Optional[str] = Field(default=None, index=True)
    unit: Optional[str] = Field(default=None)
    aliases: List[str] = Field(default=[], sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PatientTest(SQLModel, table=True):
    """
    Individual patient test result, normalized and linked to standardized definitions.
    
    This is the main table for the global spreadsheet view, enabling:
    - Aggregation across patients for a specific test
    - Pivot table: Patients × Tests
    - Time-series analysis of test results
    """
    __tablename__ = "patient_test"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Link to source document
    document_id: str = Field(foreign_key="document.id", index=True)
    
    # Link to standardized test definition (nullable for unmapped tests)
    test_definition_id: Optional[int] = Field(
        default=None, 
        foreign_key="standardized_test_definition.id", 
        index=True
    )
    
    # Patient information
    patient_name: Optional[str] = Field(default=None, index=True)
    patient_id: Optional[str] = Field(default=None, index=True)
    
    # Test details
    original_test_name: str  # Name as written in the original report
    standardized_test_name: Optional[str] = Field(default=None, index=True)  # Canonical name
    value: str  # Original value string
    numeric_value: Optional[float] = Field(default=None)  # Parsed numeric value
    text_value: Optional[str] = Field(default=None)  # Text/qualitative value
    value_type: str = Field(default="unknown")  # "numeric", "text", "mixed", "unknown"
    unit: Optional[str] = Field(default=None)
    reference_range: Optional[str] = Field(default=None)
    flag: Optional[str] = Field(default=None)  # H/L/N
    category: Optional[str] = Field(default=None, index=True)
    loinc_code: Optional[str] = Field(default=None)
    method: Optional[str] = Field(default=None)  # Test method (e.g., "Immunoturbidimetric")
    
    # Standardization metadata
    standardization_confidence: float = Field(default=0.0)
    match_type: Optional[str] = Field(default=None)  # exact, fuzzy, semantic, llm, unknown
    
    # Timestamps
    test_date: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TestSynonym(SQLModel, table=True):
    """
    Learned synonyms for test names discovered through semantic matching.
    
    When the LLM maps an unknown term to a canonical name, we store it here
    for faster future lookups.
    """
    __tablename__ = "test_synonym"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    original_term: str = Field(unique=True, index=True)
    canonical_name: str = Field(index=True)
    test_definition_id: Optional[int] = Field(
        default=None,
        foreign_key="standardized_test_definition.id"
    )
    confidence: float = Field(default=0.8)
    source: str = Field(default="llm")  # llm, manual, semantic
    created_at: datetime = Field(default_factory=datetime.utcnow)
