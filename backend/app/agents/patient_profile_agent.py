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

from app.llm import GeminiLLMService, LLMServiceType, get_llm_service
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

    def __init__(self, llm_service: Optional[LLMServiceType] = None) -> None:
        self.llm_service = llm_service or get_llm_service()

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

        result = ExtractedPatientResult(
            patient_profile_id=patient_id,
            profile=profile,
            missing_information=missing_fields,
            evidence=evidence_list,
            source_type="patient_json",
            source_document=source_document,
        )
        return self._populate_compatibility_fields(
            result, source_document=source_document, source_type="patient_json"
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
        try:
            raw_json = await self.llm_service.generate_json(
                prompt=prompt.strip(),
                system_instruction=PATIENT_NARRATIVE_SYSTEM_INSTRUCTION,
                temperature=0.0,
            )
            if not isinstance(raw_json, dict):
                raise ValueError("LLM returned non-dictionary format for patient extraction.")
        except Exception as err:
            logger.warning(
                "Patient LLM extraction failed (%s: %s), falling back to deterministic extraction...",
                type(err).__name__,
                err,
            )
            raw_json = self._extract_patient_from_pdf_deterministic(pdf_doc, assigned_id)

        # Process through deterministic pipeline to normalize models and enforce missing info logic
        result = self.process_json(raw_json, source_document=pdf_doc.filename)
        result.source_type = "patient_pdf"

        # Incorporate page evidence from extraction
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

        return self._populate_compatibility_fields(
            result, source_document=pdf_doc.filename, source_type="patient_pdf"
        )

    def _populate_compatibility_fields(
        self,
        result: ExtractedPatientResult,
        source_document: Optional[str] = None,
        source_type: str = "patient_json",
    ) -> ExtractedPatientResult:
        """Populate UI compatibility fields (lab_values, missing_information objects, extractedFields)."""
        extracted_fields: List[str] = []
        if result.patient_profile_id and not result.patient_profile_id.startswith("PAT-"):
            extracted_fields.append("patient_id")
            extracted_fields.append("patient_profile_id")

        demo = result.profile.demographics
        if demo.age is not None:
            extracted_fields.append("age")
            extracted_fields.append("demographics.age")
        if demo.sex is not None and demo.sex.value != "unknown":
            extracted_fields.append("sex")
            extracted_fields.append("demographics.sex")
        if demo.pregnancy_status is not None and demo.pregnancy_status.value != "unknown":
            extracted_fields.append("pregnancy_status")
            extracted_fields.append("demographics.pregnancy_status")
        if demo.breastfeeding_status is not None:
            extracted_fields.append("breastfeeding_status")
            extracted_fields.append("demographics.breastfeeding_status")
        if demo.height_cm is not None:
            extracted_fields.append("height")
            extracted_fields.append("demographics.height_cm")
        if demo.weight_kg is not None:
            extracted_fields.append("weight")
            extracted_fields.append("demographics.weight_kg")

        clin = result.profile.clinical_status
        if clin.ecog_performance_status is not None:
            extracted_fields.append("ecog_performance_status")
            extracted_fields.append("clinical_status.ecog_performance_status")
        if clin.active_serious_infection is not None:
            extracted_fields.append("active_serious_infection")
            extracted_fields.append("clinical_status.active_serious_infection")
        if clin.uncontrolled_cardiac_disease is not None:
            extracted_fields.append("uncontrolled_cardiac_disease")
            extracted_fields.append("clinical_status.uncontrolled_cardiac_disease")

        tx = result.profile.treatment_history
        if tx.recent_systemic_anticancer_therapy is not None:
            extracted_fields.append("recent_systemic_anticancer_therapy")
            extracted_fields.append("treatment_history.recent_systemic_anticancer_therapy")

        # 2. Build lab_values array for UI consumption
        lab_values: List[Dict[str, Any]] = []
        labs = result.profile.labs
        lab_mapping = [
            ("egfr", "eGFR", "mL/min/1.73m²"),
            ("anc", "Absolute Neutrophil Count (ANC)", "cells/mcL"),
            ("platelets", "Platelet Count", "cells/mcL"),
            ("hemoglobin", "Hemoglobin", "g/dL"),
            ("ast", "AST", "U/L"),
            ("alt", "ALT", "U/L"),
            ("bilirubin", "Total Bilirubin", "mg/dL"),
        ]
        for attr, display_name, def_unit in lab_mapping:
            lv = getattr(labs, attr, None)
            if lv is not None and lv.value is not None:
                extracted_fields.append(attr)
                extracted_fields.append(f"labs.{attr}")
                lab_values.append({
                    "name": display_name,
                    "value": lv.value,
                    "unit": lv.unit or def_unit,
                    "reference_range": lv.reference_range or None,
                })
        for k, v in labs.other_labs.items():
            if v is not None and v.value is not None:
                extracted_fields.append(f"labs.{k}")
                lab_values.append({
                    "name": k.replace("_", " ").title(),
                    "value": v.value,
                    "unit": v.unit or "",
                    "reference_range": v.reference_range or None,
                })
        result.profile.lab_values = lab_values

        # 3. Build missing_information structured objects for UI list
        missing_objs: List[Dict[str, Any]] = []
        for mf in result.missing_information:
            parts = mf.split(".", 1)
            cat = parts[0] if len(parts) > 1 else "general"
            field_name = parts[1] if len(parts) > 1 else parts[0]
            missing_objs.append({
                "field": field_name,
                "status": "missing",
                "category": cat,
                "description": f"{field_name.replace('_', ' ').capitalize()} is not documented in the medical record.",
            })
        result.profile.missing_information = missing_objs

        # 4. Top-level fields
        result.extractedFields = extracted_fields
        result.extracted_fields = extracted_fields
        result.sourceDocument = source_document or result.source_document
        is_pdf = "pdf" in (source_type or "").lower() or (source_document and source_document.lower().endswith(".pdf"))
        result.sourceType = "Uploaded PDF" if is_pdf else "Uploaded JSON"
        result.source_type = "patient_pdf" if is_pdf else "patient_json"
        result.source_document = result.sourceDocument

        # 5. Profile metadata
        result.profile.metadata = {
            "source": result.sourceType,
            "source_document": result.sourceDocument,
            "extracted_fields": extracted_fields,
            "ecog_score": clin.ecog_performance_status,
            "active_serious_infection": clin.active_serious_infection,
            "uncontrolled_cardiac_disease": clin.uncontrolled_cardiac_disease,
            "recent_systemic_anticancer_therapy": tx.recent_systemic_anticancer_therapy,
        }
        return result

    def _extract_patient_from_pdf_deterministic(
        self,
        pdf_doc: PDFDocument,
        patient_profile_id: str,
    ) -> Dict[str, Any]:
        """Deterministic regex-based extraction from PDF text pages when LLM is unavailable."""
        data: Dict[str, Any] = {
            "patient_profile_id": patient_profile_id,
            "demographics": {},
            "clinical_status": {},
            "labs": {},
            "vital_signs": {},
            "conditions": [],
            "medications": [],
            "allergies": [],
            "treatment_history": {},
            "page_evidence": [],
        }

        for page in pdf_doc.pages:
            text = page.text or ""
            page_num = page.page_number
            for line in text.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue

                # Patient ID
                m_id = re.search(r"(?:patient\s*(?:id|identifier)|pt[-_\s]*id)\s*[:#-]?\s*([A-Za-z0-9_-]+)", line_str, re.I)
                if m_id and not data.get("_id_extracted"):
                    data["patient_profile_id"] = m_id.group(1).strip()
                    data["_id_extracted"] = True
                    data["page_evidence"].append({
                        "field": "patient_profile_id",
                        "value": m_id.group(1).strip(),
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Age
                m_age = re.search(r"(?:age|years\s*old)\s*[:=]?\s*(\d{1,3})|(\d{1,3})\s*(?:years?\s*old|y/?o)", line_str, re.I)
                if m_age and "age" not in data["demographics"]:
                    val = int(m_age.group(1) or m_age.group(2))
                    data["demographics"]["age"] = val
                    data["page_evidence"].append({
                        "field": "demographics.age",
                        "value": val,
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Sex
                m_sex = re.search(r"\b(female|male|woman|man)\b", line_str, re.I)
                if m_sex and "sex" not in data["demographics"]:
                    s = "female" if "fem" in m_sex.group(1).lower() or "woman" in m_sex.group(1).lower() else "male"
                    data["demographics"]["sex"] = s
                    data["page_evidence"].append({
                        "field": "demographics.sex",
                        "value": s,
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Pregnancy
                if re.search(r"\bnot\s*pregnant\b|\bnegative\s*pregnancy\b|\bpregnancy\s*[:=]?\s*(?:no|negative|not\s*pregnant)\b", line_str, re.I):
                    data["demographics"]["pregnancy_status"] = "not_pregnant"
                    data["page_evidence"].append({
                        "field": "demographics.pregnancy_status",
                        "value": "not_pregnant",
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })
                elif re.search(r"\bpregnant\b", line_str, re.I) and "not pregnant" not in line_str.lower():
                    data["demographics"]["pregnancy_status"] = "pregnant"
                    data["page_evidence"].append({
                        "field": "demographics.pregnancy_status",
                        "value": "pregnant",
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Breastfeeding
                if re.search(r"breastfeeding\s*[:=]?\s*(?:no|negative|false|denied|denies)|not\s*breastfeeding", line_str, re.I):
                    data["demographics"]["breastfeeding_status"] = False
                    data["page_evidence"].append({
                        "field": "demographics.breastfeeding_status",
                        "value": False,
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # ECOG
                m_ecog = re.search(r"ecog(?:\s*performance\s*status)?\s*[:=]?\s*(\d)", line_str, re.I)
                if m_ecog and "ecog_performance_status" not in data["clinical_status"]:
                    data["clinical_status"]["ecog_performance_status"] = int(m_ecog.group(1))
                    data["page_evidence"].append({
                        "field": "clinical_status.ecog_performance_status",
                        "value": int(m_ecog.group(1)),
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Active serious infection
                if re.search(r"(?:no\s*active\s*(?:serious\s*)?infection|active\s*(?:serious\s*)?infection\s*[:=]?\s*(?:no|none|negative|false|denied|denies))", line_str, re.I):
                    data["clinical_status"]["active_serious_infection"] = False
                    data["page_evidence"].append({
                        "field": "clinical_status.active_serious_infection",
                        "value": False,
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Cardiac disease
                if re.search(r"(?:no\s*uncontrolled\s*cardiac(?:\s*disease)?|uncontrolled\s*cardiac(?:\s*disease)?\s*[:=]?\s*(?:no|none|negative|false|denied|denies))", line_str, re.I):
                    data["clinical_status"]["uncontrolled_cardiac_disease"] = False
                    data["page_evidence"].append({
                        "field": "clinical_status.uncontrolled_cardiac_disease",
                        "value": False,
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # eGFR
                m_egfr = re.search(r"(?:estimated\s*glomerular\s*filtration\s*rate(?:\s*\(egfr\))?|egfr)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z0-9/²\^]+)?", line_str, re.I)
                if m_egfr and "egfr" not in data["labs"]:
                    val = float(m_egfr.group(1))
                    u = m_egfr.group(2) or "mL/min/1.73m²"
                    data["labs"]["egfr"] = {"value": val, "unit": u}
                    data["page_evidence"].append({
                        "field": "labs.egfr",
                        "value": val,
                        "unit": u,
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # ANC
                m_anc = re.search(r"(?:absolute\s*neutrophil\s*count(?:\s*\(anc\))?|anc)\s*[:=]?\s*([0-9,]+(?:\.[0-9]+)?)\s*([a-zA-Z0-9/]+)?", line_str, re.I)
                if m_anc and "anc" not in data["labs"]:
                    val = float(m_anc.group(1).replace(",", ""))
                    u = m_anc.group(2) or "cells/mcL"
                    data["labs"]["anc"] = {"value": val, "unit": u}
                    data["page_evidence"].append({
                        "field": "labs.anc",
                        "value": val,
                        "unit": u,
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Platelets
                m_plt = re.search(r"(?:platelet(?:s|\s*count)?(?:\s*\(plt\))?|plt)\s*[:=]?\s*([0-9,]+(?:\.[0-9]+)?)\s*([a-zA-Z0-9/]+)?", line_str, re.I)
                if m_plt and "platelets" not in data["labs"]:
                    val = float(m_plt.group(1).replace(",", ""))
                    u = m_plt.group(2) or "cells/mcL"
                    data["labs"]["platelets"] = {"value": val, "unit": u}
                    data["page_evidence"].append({
                        "field": "labs.platelets",
                        "value": val,
                        "unit": u,
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Blood pressure
                m_bp = re.search(r"(?:bp|blood\s*pressure)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\s*(mmHg)?", line_str, re.I)
                if m_bp and "blood_pressure" not in data["vital_signs"]:
                    sys = int(m_bp.group(1))
                    dia = int(m_bp.group(2))
                    data["vital_signs"]["blood_pressure"] = {"systolic": sys, "diastolic": dia, "unit": "mmHg"}
                    data["page_evidence"].append({
                        "field": "vital_signs.blood_pressure",
                        "value": f"{sys}/{dia}",
                        "unit": "mmHg",
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Heart rate
                m_hr = re.search(r"(?:hr|heart\s*rate|pulse)\s*[:=]?\s*(\d{2,3})\s*(?:bpm)?", line_str, re.I)
                if m_hr and "heart_rate" not in data["vital_signs"]:
                    hr_val = int(m_hr.group(1))
                    data["vital_signs"]["heart_rate"] = hr_val
                    data["page_evidence"].append({
                        "field": "vital_signs.heart_rate",
                        "value": hr_val,
                        "unit": "bpm",
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

                # Recent anticancer therapy
                if re.search(r"(?:no\s*recent\s*systemic\s*anticancer\s*therapy|systemic\s*anticancer\s*therapy\s*[:=]?\s*(?:no|none|negative|false|denied|denies))", line_str, re.I):
                    data["treatment_history"]["recent_systemic_anticancer_therapy"] = False
                    data["page_evidence"].append({
                        "field": "treatment_history.recent_systemic_anticancer_therapy",
                        "value": False,
                        "source_page": page_num,
                        "source_excerpt": line_str,
                    })

        data.pop("_id_extracted", None)
        return data
