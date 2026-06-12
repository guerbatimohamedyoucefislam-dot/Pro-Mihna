import sys
with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "db.execute('" in line and ("'pending'" in line or "'accepted'" in line or "'rejected'" in line or "'completed'" in line or "'assigned'" in line or "'active'" in line or "'worker'" in line):
        # We need to change the outer string from ' to "
        # It's usually like: db.execute('UPDATE standard_requests SET status = 'accepted' WHERE id = ?', [req_id])
        # Replace the first `'` after `db.execute(` with `"`
        line = line.replace("db.execute('", "db.execute(\"")
        # Find the end of the query string and replace it with `"`
        # Usually it's `',` or `')`
        line = line.replace("',", "\",")
        line = line.replace("')", "\")")
        # In query_db('SELECT COUNT(id) as c FROM users WHERE role='worker'', one=True)['c']
        line = line.replace("query_db('", "query_db(\"")
    new_lines.append(line)

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Fixed app.py syntax!")
