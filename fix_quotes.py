import sys
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    'role="worker"': "role='worker'",
    'role="customer"': "role='customer'",
    'role="admin"': "role='admin'",
    'status = "pending"': "status = 'pending'",
    'status = "accepted"': "status = 'accepted'",
    'status = "rejected"': "status = 'rejected'",
    'status = "completed"': "status = 'completed'",
    'status = "assigned"': "status = 'assigned'",
    'status = "active"': "status = 'active'",
    'status="pending"': "status='pending'",
    '"pending"': "'pending'",
    '"accepted"': "'accepted'",
    '"completed"': "'completed'",
    '"assigned"': "'assigned'",
    '"rejected"': "'rejected'"
}

for k, v in replacements.items():
    content = content.replace(k, v)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Replaced double quotes with single quotes in SQL queries!')
