import json
import os
from datetime import datetime

audit_log_path = "logs/audit_log.jsonl"
os.makedirs(os.path.dirname(audit_log_path), exist_ok=True)

# Delete existing to wipe out bad memory
if os.path.exists(audit_log_path):
    os.remove(audit_log_path)

examples = [
    {
        "intent": "PATIENT_SEARCH",
        "question": "show me the details of patient registration no 166637",
        "generated_sql": "SELECT pm.patientid, pm.registration_no, pm.first_name, pm.r_firstname AS arbname, pm.date_of_birth, pm.age, g.display AS gender, pm.mobile FROM fhir_patient_mst pm LEFT JOIN fhir_gender_mst g ON pm.gender = g.id WHERE pm.registration_no = '166637'"
    },
    {
        "intent": "VISIT",
        "question": "what are the visit details for registration no 166637",
        "generated_sql": "SELECT v.visit_id, v.visitno, v.visitdate, v.typeofvisit, e.firstname AS doctor_fname, e.lastname AS doctor_lname, w.display AS ward, r.display AS room, b.display AS bed FROM fhir_visit_mst v JOIN fhir_patient_mst p ON v.patientid = p.patientid LEFT JOIN fhir_emp_mst e ON v.docincharge = e.empid LEFT JOIN fhir_ward_mst w ON v.wardid = w.id LEFT JOIN fhir_room_mst r ON v.roomid = r.id LEFT JOIN fhir_bed_mst b ON v.bedid = b.id WHERE p.registration_no = '166637'"
    },
    {
        "intent": "BILLING",
        "question": "billing details for registration 166637",
        "generated_sql": "SELECT b.billno, b.billdate, b.grossamount, b.discountamount, b.netamount, b.dueamount, bt.billtypename FROM fhir_bill_mst b JOIN fhir_visit_mst v ON b.visit_id = v.visit_id JOIN fhir_patient_mst p ON v.patientid = p.patientid LEFT JOIN fhir_billtype bt ON b.billtypeid = bt.billtypeid WHERE p.registration_no = '166637'"
    },
    {
        "intent": "PRESCRIPTION",
        "question": "what is the prescription for 166637",
        "generated_sql": "SELECT drug.display AS drug_name, dtl.dosage, dtl.frequency, dtl.duration, dtl.quantity, dtl.notes, visit.visitno, pmst.datetime AS prescription_date FROM fhir_prescription_mst pmst JOIN fhir_visit_mst visit ON pmst.visitid = visit.visit_id JOIN fhir_patient_mst p ON visit.patientid = p.patientid JOIN fhir_prescription_dtl dtl ON pmst.id = dtl.preid LEFT JOIN fhir_drug_mst drug ON dtl.itemid = drug.id WHERE p.registration_no = '166637'"
    },
    {
        "intent": "PRESCRIPTION",
        "question": "show prescription for 166637",
        "generated_sql": "SELECT drug.display AS drug_name, dtl.dosage, COALESCE(freq.display, dtl.frequency) AS frequency, dtl.duration, dtl.quantity, dtl.notes, visit.visitno, pmst.datetime AS prescription_date FROM fhir_prescription_mst pmst JOIN fhir_visit_mst visit ON pmst.visitid = visit.visit_id JOIN fhir_patient_mst p ON visit.patientid = p.patientid JOIN fhir_prescription_dtl dtl ON pmst.id = dtl.preid LEFT JOIN fhir_drug_mst drug ON dtl.itemid = drug.id LEFT JOIN fhir_prescription_frequency freq ON dtl.frequency = freq.id WHERE p.registration_no = '166637'"
    },
    {
        "intent": "PRESCRIPTION",
        "question": "give drug to drug comparison for patient 166637",
        "generated_sql": "SELECT drug.display AS drug_name, dtl.dosage, dtl.frequency, dtl.duration, dtl.quantity, dtl.notes, visit.visitno, pmst.datetime AS prescription_date FROM fhir_prescription_mst pmst JOIN fhir_visit_mst visit ON pmst.visitid = visit.visit_id JOIN fhir_patient_mst p ON visit.patientid = p.patientid JOIN fhir_prescription_dtl dtl ON pmst.id = dtl.preid JOIN fhir_drug_mst drug ON dtl.itemid = drug.id WHERE p.registration_no = '166637'"
    },
    {
        "intent": "LAB",
        "question": "lab test results for patient 166637",
        "generated_sql": "SELECT ltr.test_name, ltr.param_name, ltr.result, ltr.critical, v.visitno, COALESCE(ltr.resultdttime, v.visitdate) AS timing FROM fhir_lab_test_result ltr JOIN fhir_patient_mst p ON ltr.patientid = p.patientid LEFT JOIN fhir_visit_mst v ON ltr.visitid = v.visit_id WHERE p.registration_no = '166637'"
    },
    {
        "intent": "SURGERY",
        "question": "surgery operations for 166637",
        "generated_sql": "SELECT ot.scheduleno AS schedule_no, COALESCE(srv.display, 'Not recorded') AS operation_name, ot.operationdate AS operation_date, ot.starttime, ot.endtime, v.visitno FROM fhir_ot_scheduling_mst ot JOIN fhir_visit_mst v ON ot.visitid = v.visit_id JOIN fhir_patient_mst p ON v.patientid = p.patientid LEFT JOIN fhir_ot_schedulling_dtl dtl ON ot.id = dtl.schid LEFT JOIN fhir_service_mst srv ON dtl.procedureid = srv.id WHERE p.registration_no = '166637' ORDER BY ot.operationdate DESC"
    },
    {
        "intent": "ALLERGY",
        "question": "allergies for 166637",
        "generated_sql": "SELECT COALESCE(am.display, af.display, a.display, n.allergy) AS allergy_name, n.reaction, v.visitno FROM fhir_op_nurse_assessment_dtl n LEFT JOIN fhir_allergies_mst a ON CAST(n.allergy AS CHAR) = CAST(a.code AS CHAR) LEFT JOIN fhir_allergyfoodmst af ON CAST(n.allergy AS CHAR) = CAST(af.code AS CHAR) LEFT JOIN fhir_allergymedicinemst am ON CAST(n.allergy AS CHAR) = CAST(am.code AS CHAR) JOIN fhir_patient_mst p ON n.patientid = p.patientid LEFT JOIN fhir_visit_mst v ON n.visitid = v.visit_id WHERE p.registration_no = '166637' AND n.allergy IS NOT NULL AND n.allergy != ''"
    },
    {
        "intent": "VITALS",
        "question": "vitals for 166637",
        "generated_sql": "SELECT v.visitno, t.reading_datetime AS vitals_datetime, t.systolic, t.diastolic, t.temperature, t.pulse, t.respiratory FROM fhir_tprbp_dtl t JOIN fhir_visit_mst v ON t.visit_id = v.visit_id JOIN fhir_patient_mst p ON v.patientid = p.patientid WHERE p.registration_no = '166637'"
    },
    {
        "intent": "CHIEF_COMPLAINT",
        "question": "show the chief complaints for 166637",
        "generated_sql": "SELECT a.reasonforconsultation AS chief_complaints FROM fhir_op_initial_assessment a JOIN fhir_patient_mst p ON a.patientid = p.patientid WHERE p.registration_no = '166637'"
    },
    {
        "intent": "FAMILY_HISTORY",
        "question": "is there any family history of the patient 166637",
        "generated_sql": "SELECT a.historyofillness AS family_history FROM fhir_op_initial_assessment a JOIN fhir_patient_mst p ON a.patientid = p.patientid WHERE p.registration_no = '166637'"
    },
    {
        "intent": "LAB",
        "question": "lab test results for patient 166637",
        "generated_sql": "SELECT ltr.test_name, ltr.param_name, ltr.result, ltr.critical, v.visitno, COALESCE(ltr.resultdttime, v.visitdate) AS timing FROM fhir_lab_test_result ltr JOIN fhir_patient_mst p ON ltr.patientid = p.patientid LEFT JOIN fhir_visit_mst v ON ltr.visitid = v.visit_id WHERE p.registration_no = '166637'"
    },
    {
        "intent": "LAB",
        "question": "is the lab test result is in the normal range",
        "generated_sql": "SELECT ltr.test_name, ltr.param_name, ltr.result, ltr.critical, v.visitno, COALESCE(ltr.resultdttime, v.visitdate) AS timing FROM fhir_lab_test_result ltr JOIN fhir_patient_mst p ON ltr.patientid = p.patientid LEFT JOIN fhir_visit_mst v ON ltr.visitid = v.visit_id WHERE p.registration_no = '166637'"
    },
    {
        "intent": "LAB",
        "question": "lab test results with nationality and gender for 166637",
        "generated_sql": "SELECT ltr.test_name, ltr.param_name, ltr.result, ltr.critical, v.visitno, g.display AS gender, n.display AS nationality FROM fhir_lab_test_result ltr JOIN fhir_patient_mst p ON ltr.patientid = p.patientid LEFT JOIN fhir_gender_mst g ON p.gender = g.id LEFT JOIN fhir_nationality_mst n ON p.nationality = n.id LEFT JOIN fhir_visit_mst v ON ltr.visitid = v.visit_id WHERE p.registration_no = '166637'"
    },
    {
        "intent": "FAMILY_HISTORY",
        "question": "family history for 166637",
        "generated_sql": "SELECT a.reasonforconsultation, a.historyofillness, a.initialdignosis, a.treatmentplan FROM fhir_op_initial_assessment a JOIN fhir_patient_mst p ON a.patientid = p.patientid WHERE p.registration_no = '166637'"
    },
    {
        "intent": "RADIOLOGY",
        "question": "show radiology details for patient 166637",
        "generated_sql": "SELECT res.id AS 'ID', v.visitno AS 'Visit No', v.visitdate AS 'Visit Date & Time', srv.display AS 'Service Display' FROM fhir_rad_imgresult res JOIN fhir_patient_mst p ON res.patientid = p.patientid LEFT JOIN fhir_rad_imgservices srv ON res.serviceid = srv.serviceid LEFT JOIN fhir_visit_mst v ON res.visitid = v.visit_id WHERE p.registration_no = '166637' ORDER BY res.addedon DESC"
    },
    {
        "intent": "DISCHARGE_SUMMARY",
        "question": "show discharge summary for patient 166637",
        "generated_sql": "SELECT ds.visitid, ds.final_diagnosis, ds.admission_diagnosis, ds.history, ds.hospital_course, ds.admission_medication, ds.medication AS discharge_medication, ds.laboratory, ds.radiology, ds.patient_condition, ds.remark FROM fhir_Dischargesummary ds JOIN fhir_patient_mst p ON ds.patientid = p.patientid WHERE p.registration_no = '166637' ORDER BY ds.insertedon DESC"
    }
]

with open(audit_log_path, "w") as f:
    for ex in examples:
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "session_id": "seed",
            "doctor_id": "system",
            "patient_id": "166637",
            "intent": ex["intent"],
            "question": ex["question"],
            "generated_sql": ex["generated_sql"],
            "rows_returned": 1,
            "answer": "Success",
            "execution_time_ms": 100,
            "retries": 0,
            "validation_errors": []
        }
        f.write(json.dumps(entry) + "\n")

print(f"Successfully wrote {len(examples)} examples to {audit_log_path}")
