from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Sum

class Ward(models.Model):
    NAME_CHOICES = [
        ('Nyangores', 'Nyangores'),
        ('Sigor', 'Sigor'),
        ('Chebunyo', 'Chebunyo'),
        ('Siongiroi', 'Siongiroi'),
        ('kongasis', 'kongasis'),
    ]
    name = models.CharField(max_length=50, choices=NAME_CHOICES, unique=True)
    total_allocated = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    remaining_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def __str__(self):
        return self.name

class ConstituencyBudget(models.Model):
    financial_year = models.IntegerField(default=2026, unique=True)
    total_budget = models.DecimalField(max_digits=15, decimal_places=2)
    remaining_budget = models.DecimalField(max_digits=15, decimal_places=2)

    def __str__(self):
        return f"Chepalungu CDF Budget {self.financial_year}"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.remaining_budget = self.total_budget
        super().save(*args, **kwargs)

class Allocation(models.Model):
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='allocations')
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name='allocations')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    financial_year = models.IntegerField(default=2026)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.name} - {self.amount}"

    def clean(self):
        if self.amount > self.ward.remaining_balance:
            raise ValidationError(f"Insufficient funds in {self.ward.name} ward budget. Available: {self.ward.remaining_balance}")
