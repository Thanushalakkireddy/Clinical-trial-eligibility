"""Pydantic v2 schemas for normalized patient profiles, evidence provenance, and missing information tracking.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class PregnancyStatus(str, Enum):
    PREGNANT = "pregnant"
    NOT_PREGNANT = "not_pregnant"
    UNKNOWN = "unknown"


class PatientEvidence(BaseModel):
    """Provenance for an extracted clinical fact."""

    field: str = Field(..., description="Target field path (e.g., 'labs.egfr')")
    value: Any = Field(..., description="Documented value")
    unit: Optional[str] = Field(default=None, description="Physical/biological unit if applicable")
    source: str = Field(default="patient_json", description="Data source (e.g. 'patient_json', 'patient_pdf', 'patient_input')")
    source_document: Optional[str] = Field(default=None, description="Originating document filename")
    source_page: Optional[int] = Field(default=None, description="1-indexed source page number for PDF evidence")
    source_excerpt: Optional[str] = Field(default=None, description="Direct textual excerpt from source")


class Demographics(BaseModel):
    age: Optional[int] = Field(default=None, description="Age in years")
    sex: Optional[Sex] = Field(default=None, description="Biological sex")
    pregnancy_status: Optional[PregnancyStatus] = Field(default=None, description="Pregnancy state")
    breastfeeding_status: Optional[bool] = Field(default=None, description="Breastfeeding state")
    height_cm: Optional[float] = Field(default=None, description="Height in cm")
    weight_kg: Optional[float] = Field(default=None, description="Weight in kg")


class ConditionItem(BaseModel):
    name: str = Field(..., description="Condition or diagnosis name")
    status: Optional[str] = Field(default="active", description="Status (e.g. active, resolved, historical)")
    documented: bool = Field(default=True, description="Whether documented in medical record")
    source_provenance: Optional[str] = Field(default=None, description="Provenance note")


class ClinicalStatus(BaseModel):
    ecog_performance_status: Optional[int] = Field(default=None, description="ECOG score 0-5")
    active_serious_infection: Optional[bool] = Field(default=None, description="Documented active serious infection")
    uncontrolled_cardiac_disease: Optional[bool] = Field(default=None, description="Documented uncontrolled cardiac disease")


class LabValue(BaseModel):
    value: Optional[float] = Field(default=None, description="Numeric lab measurement")
    unit: Optional[str] = Field(default=None, description="Measurement unit")
    reference_range: Optional[str] = Field(default=None, description="Reference range")


class Labs(BaseModel):
    egfr: Optional[LabValue] = Field(default=None, description="Estimated Glomerular Filtration Rate")
    anc: Optional[LabValue] = Field(default=None, description="Absolute Neutrophil Count")
    platelets: Optional[LabValue] = Field(default=None, description="Platelet count")
    hemoglobin: Optional[LabValue] = Field(default=None, description="Hemoglobin")
    ast: Optional[LabValue] = Field(default=None, description="Aspartate aminotransferase")
    alt: Optional[LabValue] = Field(default=None, description="Alanine aminotransferase")
    bilirubin: Optional[LabValue] = Field(default=None, description="Total bilirubin")
    other_labs: Dict[str, LabValue] = Field(default_factory=dict, description="Other documented laboratory tests")


class BloodPressure(BaseModel):
    systolic: Optional[int] = Field(default=None, description="Systolic blood pressure (mmHg)")
    diastolic: Optional[int] = Field(default=None, description="Diastolic blood pressure (mmHg)")
    unit: str = Field(default="mmHg", description="Pressure unit")


class VitalSigns(BaseModel):
    blood_pressure: Optional[BloodPressure] = Field(default=None, description="Blood pressure")
    heart_rate: Optional[int] = Field(default=None, description="Heart rate (bpm)")
    temperature_c: Optional[float] = Field(default=None, description="Body temperature in Celsius")


class AllergyItem(BaseModel):
    substance: str = Field(..., description="Allergen substance")
    severity: Optional[str] = Field(default=None, description="Reaction severity")
    documented: bool = Field(default=True, description="Documented in record")


class MedicationItem(BaseModel):
    name: str = Field(..., description="Medication name")
    dose: Optional[str] = Field(default=None, description="Dose")
    frequency: Optional[str] = Field(default=None, description="Frequency")
    status: Optional[str] = Field(default="active", description="Medication status")


class TreatmentHistory(BaseModel):
    recent_systemic_anticancer_therapy: Optional[bool] = Field(default=None, description="Recent anticancer systemic therapy")
    prior_therapies: List[str] = Field(default_factory=list, description="Documented past treatments")
    last_treatment_date: Optional[str] = Field(default=None, description="Date of last treatment")


class PatientProfile(BaseModel):
    """Normalized structured patient profile containing only documented facts."""

    patient_profile_id: str = Field(..., description="Unique patient profile identifier")
    demographics: Demographics = Field(default_factory=Demographics)
    conditions: List[ConditionItem] = Field(default_factory=list)
    clinical_status: ClinicalStatus = Field(default_factory=ClinicalStatus)
    labs: Labs = Field(default_factory=Labs)
    vital_signs: VitalSigns = Field(default_factory=VitalSigns)
    allergies: List[AllergyItem] = Field(default_factory=list)
    medications: List[MedicationItem] = Field(default_factory=list)
    treatment_history: TreatmentHistory = Field(default_factory=TreatmentHistory)
    lab_values: List[Dict[str, Any]] = Field(default_factory=list, description="Normalized lab items list for UI consumption")
    medical_history: List[Dict[str, Any]] = Field(default_factory=list, description="Medical history items list")
    missing_information: List[Dict[str, Any]] = Field(default_factory=list, description="Structured missing info objects for UI consumption")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary")
    clinical_notes_raw: Optional[str] = Field(default=None, description="Raw clinical notes text if any")


class ExtractedPatientResult(BaseModel):
    """Result of patient profile extraction including missing fields and evidence citations."""

    patient_profile_id: str = Field(..., description="Patient identifier")
    profile: PatientProfile = Field(..., description="Normalized patient clinical profile")
    missing_information: List[str] = Field(default_factory=list, description="Explicitly missing clinically relevant fields")
    evidence: List[PatientEvidence] = Field(default_factory=list, description="Auditable provenance records")
    source_type: str = Field(default="patient_json", description="Origin: 'patient_json' | 'patient_pdf' | 'patient_input'")
    source_document: Optional[str] = Field(default=None, description="Filename of source document")
    extractedFields: List[str] = Field(default_factory=list, description="List of extracted field names for frontend compatibility")
    extracted_fields: List[str] = Field(default_factory=list, description="Snake_case list of extracted field names")
    sourceDocument: Optional[str] = Field(default=None, description="CamelCase alias for source document")
    sourceType: Optional[str] = Field(default=None, description="Display source type ('Uploaded PDF' | 'Uploaded JSON')")
