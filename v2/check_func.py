from database.connection_pool import get_connection
conn = get_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT ROUTINE_NAME FROM information_schema.ROUTINES WHERE ROUTINE_TYPE='FUNCTION'")
funcs = [f['ROUTINE_NAME'].lower() for f in cur.fetchall()]
conn.close()

sp_funcs = ['fn_getsurchargeonbillingclass', 'fn_doctorfullname', 'fn_getschemediscount']
for f in sp_funcs:
    if f in funcs:
        print(f + ' -> YES')
    else:
        print(f + ' -> NO')
