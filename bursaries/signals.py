# All business logic has been moved out of signals and into the service layer
# See students/services.py for allocation logic

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Allocation, ConstituencyBudget, Ward
from students.models import Student

# Note: Automatic budget deduction triggers have been removed.
# This prevents premature deduction when a student is created but not yet approved.
