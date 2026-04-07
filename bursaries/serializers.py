from rest_framework import serializers
from .models import Ward, ConstituencyBudget, Allocation

class WardSerializer(serializers.ModelSerializer):
    student_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Ward
        fields = '__all__'

class ConstituencyBudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConstituencyBudget
        fields = '__all__'

class AllocationSerializer(serializers.ModelSerializer):
    student_name = serializers.ReadOnlyField(source='student.name')
    ward_name = serializers.ReadOnlyField(source='ward.name')

    class Meta:
        model = Allocation
        fields = '__all__'
