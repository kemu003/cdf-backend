from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Count, Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce
from .models import Ward, ConstituencyBudget, Allocation
from .serializers import WardSerializer, ConstituencyBudgetSerializer, AllocationSerializer

class WardViewSet(viewsets.ModelViewSet):
    queryset = Ward.objects.annotate(student_count=Count('students'))
    serializer_class = WardSerializer

class ConstituencyBudgetViewSet(viewsets.ModelViewSet):
    queryset = ConstituencyBudget.objects.all()
    serializer_class = ConstituencyBudgetSerializer

    @action(detail=False, methods=['get'])
    def overview(self, request):
        budget = ConstituencyBudget.objects.filter(financial_year=2026).first()
        if not budget:
            return Response({"error": "Budget for 2026 not found"}, status=status.HTTP_404_NOT_FOUND)

        # Auto-fix: create missing Allocation records for students
        # that were added before the signal existed.
        from students.models import Student
        existing_allocation_student_ids = Allocation.objects.values_list('student_id', flat=True)
        students_missing_alloc = Student.objects.filter(
            amount__gt=0
        ).exclude(id__in=existing_allocation_student_ids)
        for student in students_missing_alloc:
            # Create allocation WITHOUT triggering signal deduction
            # by directly inserting (the remaining_balance will be
            # computed dynamically below anyway)
            Allocation.objects.create(
                student=student,
                ward=student.ward,
                amount=student.amount,
                financial_year=2026,
            )

        # Compute ward data with dynamic remaining_balance using Subqueries
        # This avoids SQL Cartesian product errors when combining multiple annotations
        from django.db.models import Subquery, OuterRef
        
        student_count_sq = Student.objects.filter(ward=OuterRef('pk')).values('ward').annotate(cnt=Count('id')).values('cnt')
        spent_sq = Allocation.objects.filter(ward=OuterRef('pk')).values('ward').annotate(total=Sum('amount')).values('total')
        
        wards = Ward.objects.annotate(
            student_count=Coalesce(Subquery(student_count_sq), Value(0)),
            spent=Coalesce(Subquery(spent_sq, output_field=DecimalField()), Value(0), output_field=DecimalField())
        )

        # Build ward data manually so remaining_balance is dynamic
        ward_data = []
        for w in wards:
            ward_data.append({
                'id': w.id,
                'name': w.name,
                'total_allocated': w.total_allocated,
                'remaining_balance': w.total_allocated - w.spent,
                'student_count': w.student_count,
            })

        # Total budget = what admin set (editable)
        total_budget = budget.total_budget

        # Allocated to students = sum of all Allocation amounts
        allocated_to_students = Allocation.objects.filter(
            financial_year=2026
        ).aggregate(
            total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
        )['total']

        remaining_budget = total_budget - allocated_to_students

        return Response({
            "budget_id": budget.id,
            "total_budget": total_budget,
            "remaining_budget": remaining_budget,
            "allocated_budget": allocated_to_students,
            "wards": ward_data
        })

class AllocationViewSet(viewsets.ModelViewSet):
    queryset = Allocation.objects.all()
    serializer_class = AllocationSerializer

    def create(self, request, *args, **kwargs):
        # The 'clean' method in models will handle validation during full_clean
        # but we can also handle it here for better API errors
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        amount = serializer.validated_data['amount']
        ward = serializer.validated_data['ward']
        
        if amount > ward.remaining_balance:
            return Response(
                {"error": f"Insufficient funds in {ward.name} ward budget. Available: {ward.remaining_balance}"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
