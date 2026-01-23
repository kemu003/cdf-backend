import os
import sys

sys.path.append('/home/rapstari/bureti-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from students.sms import send_sms_notification

# Test with a known good phone number
phone = "254725674910"
message = "Test from cPanel Python script"

success, response = send_sms_notification(phone, message)
print(f"Success: {success}")
print(f"Response: {response}")