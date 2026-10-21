
from database.connection_pool import get_connection

conn = get_connection()
cur = conn.cursor()

drop_1 = 'DROP FUNCTION IF EXISTS fhir_fn_doctorfullname'
create_1 = '''
CREATE FUNCTION fhir_fn_doctorfullname(DoctorID INT)  
RETURNS VARCHAR(150)
DETERMINISTIC
BEGIN  
 DECLARE v_DocName VARCHAR(150);
 DECLARE v_EmpType VARCHAR(50);

 SELECT EmpType INTO v_EmpType FROM fhir_employee_mst WHERE EmpId = DoctorID LIMIT 1;

 SELECT CONCAT(
  IF(FirstName IS NULL OR FirstName = '', '', CONCAT(FirstName, ' ')),
  IF(MiddleName IS NULL OR MiddleName = '', '', CONCAT(MiddleName, ' ')),
  IF(LastName IS NULL OR LastName = '', '', CONCAT(LastName, ' '))
 ) INTO v_DocName
 FROM fhir_employee_mst  
 WHERE EmpID = DoctorID LIMIT 1;

 IF UPPER(v_EmpType) = 'DOC' THEN
    SET v_DocName = CONCAT('Dr. ', v_DocName);
 END IF;

 RETURN v_DocName;
END
'''

drop_2 = 'DROP FUNCTION IF EXISTS fhir_fn_getschemediscount'
create_2 = '''
CREATE FUNCTION fhir_fn_getschemediscount(p_SchemeID INT, p_Category INT)
RETURNS FLOAT
DETERMINISTIC
BEGIN
	DECLARE v_Percentage FLOAT;
	
	SELECT Discount INTO v_Percentage
	FROM fhir_schemediscount
	WHERE SchemeID = p_SchemeID AND serviceCatID = p_Category
    LIMIT 1;
	
	RETURN IFNULL(v_Percentage, 0);
END
'''

drop_3 = 'DROP FUNCTION IF EXISTS fhir_fn_getsurchargeonbillingclass'
create_3 = '''
CREATE FUNCTION fhir_fn_getsurchargeonbillingclass(pBillingClassId INT) 
RETURNS FLOAT
DETERMINISTIC
BEGIN
	DECLARE v_SurchargePerc FLOAT;
    
	SELECT IFNULL(SurchargePer, 0) INTO v_SurchargePerc 
    FROM fhir_billingclass 
    WHERE BillingClassID = pBillingClassId
    LIMIT 1;
    
	RETURN IFNULL(v_SurchargePerc, 0);   
END
'''

try:
    for stmt in [drop_1, create_1, drop_2, create_2, drop_3, create_3]:
        print('Executing:', stmt.strip().split('\\n')[0])
        cur.execute(stmt)
    conn.commit()
    print('SUCCESS')
except Exception as e:
    print('ERROR:', e)
finally:
    conn.close()

