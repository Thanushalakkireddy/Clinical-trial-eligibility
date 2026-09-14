"""Patient Profile Agent implementation.

Converts structured patient JSON or narrative patient PDF records into normalized,
evidence-auditable Pydantic PatientProfile models.
Strictly adheres to:
- Missing information is explicitly tracked (missing != false, missing != 0)
- Preserves documented false and numeric zero
- No diagnosis inference
- No eligibility decisions
- Uses GeminiLLMService for narrative PDF parsing, deterministic parsing for JSON
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from app.llm.gemini_service import GeminiLLMService
from app.pdf.processor import PDFDocument
from app.schemas.patient import (
    AllergyItem,
    BloodPressure,
    ClinicalStatus,
    ConditionItem,
    Demographics,
    ExtractedPatientResult,
    Labs,
    LabValue,
    MedicationItem,
    PatientEvidence,
    PatientProfile,
    PregnancyStatus,
    Sex,
    TreatmentHistory,
    VitalSigns,
)

logger = logging.getLogger(__name__)

PATIENT_NARRATIVE_SYSTEM_INSTRUCTION = (
    "You are a clinical patient record extraction assistant. "
    "Extract only facts explicitly documented in the patient medical record pages. "
    "Do not infer diagnoses, clinical severity, or eligibility. "
    "Do not assume values not mentioned. "
    "If a value is not documented, leave it null/empty. "
    "Preserve exact numeric values and units without converting units. "
    "If a negative finding is documented (e.g. 'no active infection', 'not pregnant'), "
    "preserve it faithfully as documented false or 'not_pregnant'. "
    "For each extracted fact, provide the 1-indexed source_page and a brief source_excerpt. "
    "Never make any trial eligibility decisions."
)


def _safe_float(val: Any) -> Optional[float]:
    """Parse float safely, handling unit suffixes or string numbers.
    
    Returns float or None. Notice 0.0 is a valid float and not None.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None
        # Extract numeric leading sequence (e.g. "68 mL/min/1.73m²" -> 68.0, "185,000" -> 185000.0)
        match = re.search(r"[-+]?[0-9]*\.?[0-9]+", cleaned.replace(",", ""))
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
    return None


def _extract_unit(val: Any) -> Optional[str]:
    """Extract unit portion from string if present (e.g. '68 mL/min/1.73m²' -> 'mL/min/1.73m²')."""
    if isinstance(val, str):
        cleaned = val.strip()
        match = re.search(r"[-+]?[0-9]*\.?[0-9]+\s*(.*)", cleaned.replace(",", ""))
        if match and match.group(1):
            extracted = match.group(1).strip()
            if extracted:
                return extracted
    return None


def _safe_int(val: Any) -> Optional[int]:
    """Parse integer safely. Notice 0 is a valid integer and not None."""
    f = _safe_float(val)
    if f is None:
        return None
    return int(round(f))


def _safe_bool(val: Any) -> Optional[bool]:
    """Parse boolean safely. Strictly preserves False (does NOT return None for False)."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        cleaned = val.strip().lower()
        if cleaned in ("true", "yes", "documented", "positive", "1"):
            return True
        if cleaned in ("false", "no", "not_documented", "negative", "absent", "0"):
            return False
    return None


class PatientProfileAgent:
    """Agent that extracts and normalizes patient medical records."""

    def __init__(self, llm_service: Optional[GeminiLLMService] = None) -> None:
        self.llm_service = llm_service or GeminiLLMService()

    def process_json(
        self,
        data: Dict[str, Any],
        source_document: Optional[str] = None,
    ) -> ExtractedPatientResult:
        """Process structured JSON patient record deterministically.
        
        Extracts facts, records provenance, and tracks missing fields explicitly.
        """
        evidence_list: List[PatientEvidence] = []
        patient_id = str(
            data.get("patient_profile_id")
            or data.get("patient_id")
            or data.get("id")
            or f"PAT-{uuid.uuid4().hex[:8].upper()}"
        )

        demographics_data = data.get("demographics") or {}
        clinical_data = data.get("clinical_status") or {}
        labs_data = data.get("labs") or {}
        vitals_data = data.get("vital_signs") or {}
        conditions_data = data.get("conditions") or []
        allergies_data = data.get("allergies") or []
        meds_data = data.get("medications") or []
        history_data = data.get("treatment_history") or {}

        # 1. Demographics
        age_raw = demographics_data.get("age", data.get("age"))
        age = _safe_int(age_raw)
        if age is not None:
            evidence_list.append(
                PatientEvidence(
                    field="demographics.age",
                    value=age,
                    source="patient_json",
                    source_document=source_document,
                    source_excerpt=f"Age: {age_raw}",
                )
            )

        sex_raw = demographics_data.get("sex", data.get("sex"))
        sex = None
        if sex_raw is not None:
            s = str(sex_raw).strip().lower()
            if s in ("m", "male"):
                sex = Sex.MALE
            elif s in ("f", "female"):
                sex = Sex.FEMALE
            elif s in ("other",):
                sex = Sex.OTHER
            else:
                sex = Sex.UNKNOWN
            evidence_list.append(
                PatientEvidence(
                    field="demographics.sex",
                    value=sex.value,
                    source="patient_json",
                    source_document=source_document,
                    source_excerpt=f"Sex: {sex_raw}",
                )
            )

        preg_raw = demographics_data.get("pregnancy_status", data.get("pregnancy_status"))
        pregnancy_status = None
        if preg_raw is not None:
            p = str(preg_raw).strip().lower()
            if p in ("pregnant", "true", "yes", "positive"):
                pregnancy_status = PregnancyStatus.PREGNANT
            elif p in ("not_pregnant", "false", "no", "negative", "not pregnant"):
                pregnancy_status = PregnancyStatus.NOT_PREGNANT
            else:
                pregnancy_status = PregnancyStatus.UNKNOWN
            evidence_list.append(
                PatientEvidence(
                    field="demographics.pregnancy_status",
                    value=pregnancy_status.value,
                    source="patient_json",
                    source_document=source_document,
                    source_excerpt=f"Pregnancy status: {preg_raw}",
                )
            )

        bf_raw = demographics_data.get("breastfeeding_status", data.get("breastfeeding_status"))
        breastfeeding_status = _safe_bool(bf_raw)
        if breastfeeding_status is not None:
            evidence_list.append(
                PatientEvidence(
                    field="demographics.breastfeeding_status",
                    value=breastfeeding_status,
                    source="patient_json",
                    source_document=source_document,
                    source_excerpt=f"Breastfeeding: {bf_raw}",
                )
            )

        demographics = Demographics(
            age=age,
            sex=sex,
            pregnancy_status=pregnancy_status,
            breastfeeding_status=breastfeeding_status,
            height_cm=_safe_float(demographics_data.get("height", demographics_data.get("height_cm"))),
            weight_kg=_safe_float(demographics_data.get("weight", demographics_data.get("weight_kg"))),
        )

        # 2. Clinical Status (Handling aliases: ecog, ecog_score, ecog_performance_status)
        ecog_raw = (
            clinical_data.get("ecog_performance_status")
            if "ecog_performance_status" in clinical_data
            else clinical_data.get("ecog_score")
            if "ecog_score" in clinical_data
            else clinical_data.get("ecog")
            if "ecog" in clinical_data
            else data.get("ecog_performance_status")
            if "ecog_performance_status" in data
            else data.get("ecog_score")
            if "ecog_score" in data
            else data.get("ecog")
            if "ecog" in data
            else None
        )
        ecog = _safe_int(ecog_raw)
        if ecog is not None:
            evidence_list.append(
                PatientEvidence(
                    field="clinical_status.ecog_performance_status",
                    value=ecog,
                    source="patient_json",
                    source_document=source_document,
                    source_excerpt=f"ECOG: {ecog_raw}",
                )
            )

        # Active infection (MUST preserve False)
        inf_raw = (
            clinical_data.get("active_serious_infection")
            if "active_serious_infection" in clinical_data
            else data.get("active_serious_infection")
        )
        active_infection = _safe_bool(inf_raw)
        if active_infection is not None:
            evidence_list.append(
                PatientEvidence(
                    field="clinical_status.active_serious_infection",
                    value=active_infection,
                    source="patient_json",
                    source_document=source_document,
                    source_excerpt=f"Active serious infection: {inf_raw}",
                )
            )

        # Uncontrolled cardiac disease (MUST preserve False)
        cardiac_raw = (
            clinical_data.get("uncontrolled_cardiac_disease")
            if "uncontrolled_cardiac_disease" in clinical_data
            else data.get("uncontrolled_cardiac_disease")
        )
        cardiac_disease = _safe_bool(cardiac_raw)
        if cardiac_disease is not None:
            evidence_list.append(
                PatientEvidence(
                    field="clinical_status.uncontrolled_cardiac_disease",
                    value=cardiac_disease,
                    source="patient_json",
                    source_document=source_document,
                    source_excerpt=f"Uncontrolled cardiac disease: {cardiac_raw}",
                )
            )

        clinical_status = ClinicalStatus(
            ecog_performance_status=ecog,
            active_serious_infection=active_infection,
            uncontrolled_cardiac_disease=cardiac_disease,
        )

        # 3. Labs (ANC, Platelets, eGFR, etc. with aliases and zero-preservation)
        labs_obj, lab_evidences = self._extract_labs(labs_data, data, source_document)
        evidence_list.extend(lab_evidences)

        # 4. Vital Signs (BP, HR)
        vitals_obj, vitals_evidences = self._extract_vitals(vitals_data, data, source_document)
        evidence_list.extend(vitals_evidences)

        # 5. Conditions
        conditions_list: List[ConditionItem] = []
        if isinstance(conditions_data, list):
            for c in conditions_data:
                if isinstance(c, dict):
                    name = str(c.get("name") or c.get("condition") or "").strip()
                    if name:
                        conditions_list.append(
                            ConditionItem(
                                name=name,
                                status=str(c.get("status") or "active"),
                                documented=_safe_bool(c.get("documented")) if c.get("documented") is not None else True,
                                source_provenance=c.get("source_provenance") or "patient_json",
                            )
                        )
                elif isinstance(c, str) and c.strip():
                    conditions_list.append(ConditionItem(name=c.strip(), status="active", documented=True))

        # 6. Allergies
        allergies_list: List[AllergyItem] = []
        if isinstance(allergies_data, list):
            for a in allergies_data:
                if isinstance(a, dict):
                    sub = str(a.get("substance") or a.get("name") or "").strip()
                    if sub:
                        allergies_list.append(
                            AllergyItem(
                                substance=sub,
                                severity=a.get("severity"),
                                documented=_safe_bool(a.get("documented")) if a.get("documented") is not None else True,
                            )
                        )
                elif isinstance(a, str) and a.strip():
                    allergies_list.append(AllergyItem(substance=a.strip(), documented=True))

        # 7. Medications & Treatment History
        meds_list: List[MedicationItem] = []
        recent_anticancer: Optional[bool] = None

        if isinstance(meds_data, list):
            for m in meds_data:
                if isinstance(m, dict):
                    m_name = str(m.get("name") or m.get("medication") or "").strip()
                    if m_name:
                        meds_list.append(
                            MedicationItem(
                                name=m_name,
                                dose=str(m["dose"]) if m.get("dose") is not None else None,
                                frequency=str(m["frequency"]) if m.get("frequency") is not None else None,
                                status=str(m.get("status") or "active"),
                            )
                        )
                elif isinstance(m, str) and m.strip():
                    meds_list.append(MedicationItem(name=m.strip()))
        elif isinstance(meds_data, dict):
            # If medications is supplied as dict e.g. {"recent_systemic_anticancer_therapy": false}
            if "recent_systemic_anticancer_therapy" in meds_data:
                recent_anticancer = _safe_bool(meds_data["recent_systemic_anticancer_therapy"])

        if recent_anticancer is None:
            if "recent_systemic_anticancer_therapy" in history_data:
                recent_anticancer = _safe_bool(history_data["recent_systemic_anticancer_therapy"])
            elif "recent_systemic_anticancer_therapy" in data:
                recent_anticancer = _safe_bool(data["recent_systemic_anticancer_therapy"])

        if recent_anticancer is not None:
            evidence_list.append(
                PatientEvidence(
                    field="treatment_history.recent_systemic_anticancer_therapy",
                    value=recent_anticancer,
                    source="patient_json",
                    source_document=source_document,
                    source_excerpt=f"Recent systemic anticancer therapy: {recent_anticancer}",
                )
            )

        treatment_history = TreatmentHistory(
            recent_systemic_anticancer_therapy=recent_anticancer,
            prior_therapies=history_data.get("prior_therapies") or [],
            last_treatment_date=history_data.get("last_treatment_date"),
        )

        profile = PatientProfile(
            patient_profile_id=patient_id,
            demographics=demographics,
            conditions=conditions_list,
            clinical_status=clinical_status,
            labs=labs_obj,
            vital_signs=vitals_obj,
            allergies=allergies_list,
            medications=meds_list,
            treatment_history=treatment_history,
        )

        missing_fields = self._compute_missing_information(profile)

        return ExtractedPatientResult(
            patient_profile_id=patient_id,
            profile=profile,
            missing_information=missing_fields,
            evidence=evidence_list,
            source_type="patient_json",
            source_document=source_document,
        )

    def _extract_labs(
        self,
        labs_data: Dict[str, Any],
        root_data: Dict[str, Any],
        source_document: Optional[str],
    ) -> Tuple[Labs, List[PatientEvidence]]:
        """Extract lab values with alias resolution and zero preservation."""
        evidences: List[PatientEvidence] = []

        # Helper to parse LabValue from nested dict or direct scalar
        def _parse_lab(keys: List[str], field_name: str, default_unit: str) -> Optional[LabValue]:
            raw = None
            for k in keys:
                if k in labs_data:
                    raw = labs_data[k]
                    break
                if k in root_data:
                    raw = root_data[k]
                    break

            if raw is None:
                return None

            val: Optional[float] = None
            unit: Optional[str] = default_unit

            if isinstance(raw, dict):
                val = _safe_float(raw.get("value"))
                unit = raw.get("unit") or default_unit
            else:
                val = _safe_float(raw)
                unit_str = _extract_unit(raw)
                if unit_str:
                    unit = unit_str

            if val is not None:
                evidences.append(
                    PatientEvidence(
                        field=field_name,
                        value=val,
                        unit=unit,
                        source="patient_json",
                        source_document=source_document,
                        source_excerpt=f"{keys[0]}: {raw}",
                    )
                )
                return LabValue(value=val, unit=unit)
            return None

        egfr = _parse_lab(["egfr", "eGFR", "estimated_gfr"], "labs.egfr", "mL/min/1.73m²")
        anc = _parse_lab(["anc", "ANC", "absolute_neutrophil_count"], "labs.anc", "cells/mcL")
        platelets = _parse_lab(["platelets", "platelet_count", "platelet"], "labs.platelets", "cells/mcL")
        hemoglobin = _parse_lab(["hemoglobin", "hgb", "hb"], "labs.hemoglobin", "g/dL")
        ast = _parse_lab(["ast", "AST", "sgot"], "labs.ast", "U/L")
        alt = _parse_lab(["alt", "ALT", "sgpt"], "labs.alt", "U/L")
        bilirubin = _parse_lab(["bilirubin", "total_bilirubin", "bili"], "labs.bilirubin", "mg/dL")

        labs_obj = Labs(
            egfr=egfr,
            anc=anc,
            platelets=platelets,
            hemoglobin=hemoglobin,
            ast=ast,
            alt=alt,
            bilirubin=bilirubin,
        )
        return labs_obj, evidences

    def _extract_vitals(
        self,
        vitals_data: Dict[str, Any],
        root_data: Dict[str, Any],
        source_document: Optional[str],
    ) -> Tuple[VitalSigns, List[PatientEvidence]]:
        """Extract blood pressure and vitals preserving numeric values."""
        evidences: List[PatientEvidence] = []
        bp_raw = vitals_data.get("blood_pressure") or root_data.get("blood_pressure")
        bp_obj: Optional[BloodPressure] = None

        if isinstance(bp_raw, dict):
            sys_val = _safe_int(bp_raw.get("systolic"))
            dia_val = _safe_int(bp_raw.get("diastolic"))
            unit_val = bp_raw.get("unit") or "mmHg"
            if sys_val is not None or dia_val is not None:
                bp_obj = BloodPressure(systolic=sys_val, diastolic=dia_val, unit=unit_val)
                evidences.append(
                    PatientEvidence(
                        field="vital_signs.blood_pressure",
                        value=f"{sys_val}/{dia_val}",
                        unit=unit_val,
                        source="patient_json",
                        source_document=source_document,
                        source_excerpt=f"BP: {sys_val}/{dia_val} {unit_val}",
                    )
                )
        elif isinstance(bp_raw, str):
            # Support "125/78" or "125/78 mmHg"
            match = re.search(r"(\d+)\s*/\s*(\d+)", bp_raw)
            if match:
                sys_val = int(match.group(1))
                dia_val = int(match.group(2))
                bp_obj = BloodPressure(systolic=sys_val, diastolic=dia_val, unit="mmHg")
                evidences.append(
                    PatientEvidence(
                        field="vital_signs.blood_pressure",
                        value=f"{sys_val}/{dia_val}",
                        unit="mmHg",
                        source="patient_json",
                        source_document=source_document,
                        source_excerpt=f"BP: {bp_raw}",
                    )
                )

        hr_val = _safe_int(vitals_data.get("heart_rate") or root_data.get("heart_rate"))
        temp_val = _safe_float(vitals_data.get("temperature_c") or root_data.get("temperature_c"))

        vitals_obj = VitalSigns(
            blood_pressure=bp_obj,
            heart_rate=hr_val,
            temperature_c=temp_val,
        )
        return vitals_obj, evidences

    def _compute_missing_information(self, profile: PatientProfile) -> List[str]:
        """Compute missing core clinical attributes.
        
        CRITICAL RULE:
        Missing information must be checked with explicit `is None` checks!
        Never treat False or 0 as missing:
          - active_serious_infection=False is DOCUMENTED -> not missing.
          - eGFR=0 is DOCUMENTED -> not missing.
        """
        missing: List[str] = []

        # Demographics
        if profile.demographics.age is None:
            missing.append("demographics.age")
        if profile.demographics.sex is None or profile.demographics.sex == Sex.UNKNOWN:
            missing.append("demographics.sex")
        if profile.demographics.pregnancy_status is None or profile.demographics.pregnancy_status == PregnancyStatus.UNKNOWN:
            missing.append("demographics.pregnancy_status")
        if profile.demographics.breastfeeding_status is None:
            missing.append("demographics.breastfeeding_status")

        # Clinical status
        if profile.clinical_status.ecog_performance_status is None:
            missing.append("clinical_status.ecog_performance_status")
        if profile.clinical_status.active_serious_infection is None:
            missing.append("clinical_status.active_serious_infection")
        if profile.clinical_status.uncontrolled_cardiac_disease is None:
            missing.append("clinical_status.uncontrolled_cardiac_disease")

        # Core labs
        if profile.labs.egfr is None or profile.labs.egfr.value is None:
            missing.append("labs.egfr")
        if profile.labs.anc is None or profile.labs.anc.value is None:
            missing.append("labs.anc")
        if profile.labs.platelets is None or profile.labs.platelets.value is None:
            missing.append("labs.platelets")

        # Vital signs
        if profile.vital_signs.blood_pressure is None or profile.vital_signs.blood_pressure.systolic is None:
            missing.append("vital_signs.blood_pressure")

        # Treatment history
        if profile.treatment_history.recent_systemic_anticancer_therapy is None:
            missing.append("treatment_history.recent_systemic_anticancer_therapy")

        return missing

    async def process_pdf(
        self,
        pdf_doc: PDFDocument,
        patient_profile_id: Optional[str] = None,
    ) -> ExtractedPatientResult:
        """Process narrative patient PDF record using GeminiLLMService.
        
        Extracts facts page-by-page preserving citations and validates output with Pydantic.
        """
        if not pdf_doc.pages or pdf_doc.total_pages == 0:
            raise ValueError("Cannot extract patient profile from an empty PDF.")

        formatted_pages: List[str] = []
        for p in pdf_doc.pages:
            formatted_pages.append(
                f"--- BEGIN PATIENT RECORD PAGE {p.page_number} ---\n"
                f"{p.text}\n"
                f"--- END PATIENT RECORD PAGE {p.page_number} ---"
            )
        pages_payload = "\n\n".join(formatted_pages)

        assigned_id = patient_profile_id or f"PAT-{uuid.uuid4().hex[:8].upper()}"

        prompt = f"""
Patient Profile ID: {assigned_id}
Document Filename: {pdf_doc.filename}
Total Pages: {pdf_doc.total_pages}

PATIENT MEDICAL RECORD TEXT:
{pages_payload}

INSTRUCTIONS:
1. Extract all explicitly documented patient demographics, clinical status, laboratory values, vital signs, allergies, medications, and treatment history.
2. For each extracted value, identify its 1-indexed source_page and a short direct source_excerpt.
3. If a finding is explicitly documented as negative/normal (e.g. 'no active serious infection', 'not pregnant', 'breastfeeding: no'), record the explicit false/negative value.
4. If a value is NOT mentioned anywhere in the document, set it to null.
5. NEVER invent facts or infer diagnoses that are not stated.

Respond strictly with a JSON object conforming to this schema:
{{
  "patient_profile_id": "{assigned_id}",
  "demographics": {{
    "age": 52,
    "sex": "female",
    "pregnancy_status": "not_pregnant",
    "breastfeeding_status": false,
    "height_cm": null,
    "weight_kg": null
  }},
  "clinical_status": {{
    "ecog_performance_status": 1,
    "active_serious_infection": false,
    "uncontrolled_cardiac_disease": false
  }},
  "labs": {{
    "egfr": {{"value": 68.0, "unit": "mL/min/1.73m²"}},
    "anc": {{"value": 2400.0, "unit": "cells/mcL"}},
    "platelets": {{"value": 185000.0, "unit": "cells/mcL"}}
  }},
  "vital_signs": {{
    "blood_pressure": {{"systolic": 125, "diastolic": 78, "unit": "mmHg"}}
  }},
  "conditions": [
    {{"name": "advanced solid tumor", "status": "active", "documented": true}}
  ],
  "allergies": [],
  "medications": [],
  "treatment_history": {{
    "recent_systemic_anticancer_therapy": false
  }},
  "page_evidence": [
    {{
      "field": "labs.egfr",
      "value": 68.0,
      "unit": "mL/min/1.73m²",
      "source_page": 1,
      "source_excerpt": "eGFR: 68 mL/min/1.73m²"
    }}
  ]
}}
"""
        raw_json = await self.llm_service.generate_json(
            prompt=prompt.strip(),
            system_instruction=PATIENT_NARRATIVE_SYSTEM_INSTRUCTION,
            temperature=0.0,
        )

        if not isinstance(raw_json, dict):
            raise ValueError("LLM returned non-dictionary format for patient extraction.")

        # Process through deterministic pipeline to normalize models and enforce missing info logic
        result = self.process_json(raw_json, source_document=pdf_doc.filename)
        result.source_type = "patient_pdf"

        # Incorporate page evidence from LLM extraction
        page_evidences = raw_json.get("page_evidence") or []
        for pe in page_evidences:
            if isinstance(pe, dict) and pe.get("field") and pe.get("value") is not None:
                field_name = str(pe["field"])
                # Match existing evidence or append page-traceable evidence
                matched = False
                for ev in result.evidence:
                    if ev.field == field_name:
                        ev.source = "patient_pdf"
                        ev.source_page = _safe_int(pe.get("source_page"))
                        ev.source_excerpt = str(pe.get("source_excerpt") or "")
                        matched = True
                        break
                if not matched:
                    result.evidence.append(
                        PatientEvidence(
                            field=field_name,
                            value=pe["value"],
                            unit=pe.get("unit"),
                            source="patient_pdf",
                            source_document=pdf_doc.filename,
                            source_page=_safe_int(pe.get("source_page")),
                            source_excerpt=str(pe.get("source_excerpt") or ""),
                        )
                    )

        return result
