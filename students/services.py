from django.db import transaction
from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from students.models import Student
from bursaries.models import Ward, Allocation

class InsufficientFundsError(Exception):
    pass

@transaction.atomic
def approve_student(student_id, user):
    """
    Approves a student and explicitly creates an allocation.
    Uses select_for_update() to lock the Ward row, preventing over-allocation 
    even under concurrent request scenarios.
    """
    # 1. Lock the student to prevent concurrent approvals of the same student
    student = Student.objects.select_for_update().get(id=student_id)
    
    if student.status == 'approved' or student.status == 'disbursed':
        return student, False, "Student is already approved or disbursed."
    
    if student.amount is None or student.amount <= 0:
        raise ValueError("Student allocation amount must be greater than zero.")

    # 2. Lock the ward row. This forces any concurrent approval requests 
    #    for this same ward to wait sequentially in line.
    ward = Ward.objects.select_for_update().get(id=student.ward_id)
    
    # 3. Calculate exactly how much money has already been spent for this ward
    spent = Allocation.objects.filter(ward=ward).aggregate(
        total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
    )['total']
    
    # 4. Check if the ward can afford this student
    if student.amount > (ward.total_allocated - spent):
        raise InsufficientFundsError(
            f"Insufficient funds in {ward.name} ward budget. "
            f"Requested: {student.amount}, Available: {ward.total_allocated - spent}"
        )
    
    # 5. All checks passed - proceed to approve
    student.status = 'approved'
    student.date_processed = timezone.now()
    student.updated_by = user
    student.save()
    
    # 6. Explicitly create the Allocation to mark the funds as spent
    Allocation.objects.create(
        student=student,
        ward=ward,
        amount=student.amount,
        financial_year=2026
    )
    
    return student, True, "Approved successfully"
