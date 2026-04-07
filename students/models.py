# students/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

class Student(models.Model):
    EDUCATION_LEVEL_CHOICES = [
        ('high_school', 'High School'),
        ('college', 'College'),
        ('university', 'University'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('disbursed', 'Disbursed'),
        ('rejected', 'Rejected'),
    ]
    
    SMS_STATUS_CHOICES = [
        ('not_sent', 'Not Sent'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('partial', 'Partial'),
    ]
    
    YEAR_CHOICES = [
        ('Form 1', 'Form 1'),
        ('Form 2', 'Form 2'),
        ('Form 3', 'Form 3'),
        ('Form 4', 'Form 4'),
        ('1st Year', '1st Year'),
        ('2nd Year', '2nd Year'),
        ('3rd Year', '3rd Year'),
        ('4th Year', '4th Year'),
    ]
    
    WARD_CHOICES = [
        ('Nyangores', 'Nyangores'),
        ('Sigor', 'Sigor'),
        ('Chebunyo', 'Chebunyo'),
        ('Siongiroi', 'Siongiroi'),
        ('kongasis', 'kongasis'),
    ]
    
    SPONSORSHIP_SOURCE_CHOICES = [
        ('cdf', 'CDF Fund'),
        ('mp', 'Member of Parliament'),
        ('other', 'Other Sponsor'),
    ]
    
    # Personal Information
    name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    registration_no = models.CharField(
        max_length=50,
        unique=True,
        help_text="Student's school registration/admission number"
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    guardian_phone = models.CharField(max_length=20)
    
    # Education Information
    education_level = models.CharField(max_length=20, choices=EDUCATION_LEVEL_CHOICES)
    institution = models.CharField(max_length=200)
    school_name = models.CharField(max_length=200, null=True, blank=True)
    course = models.CharField(max_length=200, blank=True)
    year = models.CharField(max_length=20, choices=YEAR_CHOICES)
    
    # Allocation Information
    ward = models.ForeignKey('bursaries.Ward', on_delete=models.PROTECT, related_name='students')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Sponsorship Information - NEW FIELDS
    sponsorship_source = models.CharField(
        max_length=20,
        choices=SPONSORSHIP_SOURCE_CHOICES,
        default='cdf',
        verbose_name="Sponsorship Source"
    )
    
    # Sponsor-specific fields (for MP and Other sponsors)
    sponsor_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Sponsor Name (Optional)",
        help_text="e.g., Hon. MP Name, Company Name, etc."
    )
    
    sponsorship_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="Sponsorship Date"
    )
    
    sponsorship_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Sponsorship Amount (KES)",
        help_text="Amount sponsored by sponsor"
    )
    
    sponsor_details = models.TextField(
        blank=True,
        null=True,
        verbose_name="Sponsor Details (Optional)",
        help_text="Additional details about the sponsorship"
    )
    
    # Status Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sms_status = models.CharField(max_length=20, choices=SMS_STATUS_CHOICES, default='not_sent')
    
    # SMS Tracking
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    sms_sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sms_sent_students'
    )
    
    # Rejection tracking
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Dates
    date_applied = models.DateTimeField(default=timezone.now)
    date_processed = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='students_created'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='students_updated'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Student'
        verbose_name_plural = 'Students'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['education_level']),
            models.Index(fields=['ward']),
            models.Index(fields=['sms_status']),
            models.Index(fields=['date_applied']),
            models.Index(fields=['registration_no']),
            models.Index(fields=['sponsorship_source']),  # Added for sponsorship filtering
        ]
    
    def __str__(self):
        return f"{self.name} - {self.registration_no}"
    
    def clean(self):
        """Validate sponsorship data based on sponsorship source"""
        errors = {}
        
        # If sponsored by MP or Other, validate related fields
        if self.sponsorship_source in ['mp', 'other']:
            if not self.sponsorship_date:
                errors['sponsorship_date'] = "Sponsorship date is required for MP/Other sponsorship"
            if not self.sponsorship_amount or self.sponsorship_amount <= 0:
                errors['sponsorship_amount'] = "Valid sponsorship amount is required for MP/Other sponsorship"
        
        # If CDF sponsored, clear sponsor-specific fields
        elif self.sponsorship_source == 'cdf':
            self.sponsor_name = None
            self.sponsorship_date = None
            self.sponsorship_amount = None
            self.sponsor_details = None
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        # For high school students, ensure course is empty
        if self.education_level == 'high_school':
            self.course = ''
        
        # Set date_processed if status is approved/disbursed/rejected and not already set
        if self.status in ['approved', 'disbursed', 'rejected'] and not self.date_processed:
            self.date_processed = timezone.now()
        
        # Clean the data before saving
        self.clean()
        
        super().save(*args, **kwargs)
    
    def get_education_level_display(self):
        """Get human-readable education level"""
        return dict(self.EDUCATION_LEVEL_CHOICES).get(self.education_level, self.education_level)
    
    def get_status_display(self):
        """Get human-readable status"""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)
    
    def get_sms_status_display(self):
        """Get human-readable SMS status"""
        return dict(self.SMS_STATUS_CHOICES).get(self.sms_status, self.sms_status)
    
    def get_year_display(self):
        """Get human-readable year"""
        return dict(self.YEAR_CHOICES).get(self.year, self.year)
    
    def get_ward_display(self):
        """Get human-readable ward"""
        return dict(self.WARD_CHOICES).get(self.ward, self.ward)
    
    def get_sponsorship_source_display(self):
        """Get human-readable sponsorship source"""
        return dict(self.SPONSORSHIP_SOURCE_CHOICES).get(self.sponsorship_source, self.sponsorship_source)
    
    @property
    def is_cdf_sponsored(self):
        """Check if student is CDF sponsored"""
        return self.sponsorship_source == 'cdf'
    
    @property
    def is_mp_sponsored(self):
        """Check if student is MP sponsored"""
        return self.sponsorship_source == 'mp'
    
    @property
    def is_other_sponsored(self):
        """Check if student is other sponsored"""
        return self.sponsorship_source == 'other'
    
    @property
    def total_allocation(self):
        """Get total allocation amount (CDF + sponsorship)"""
        if self.sponsorship_amount and self.sponsorship_amount > 0:
            return self.amount + self.sponsorship_amount
        return self.amount
    
    @classmethod
    def get_statistics(cls):
        """Get comprehensive statistics about students"""
        from django.db.models import Sum, Count, Q
        
        stats = {
            'total': cls.objects.count(),
            'pending': cls.objects.filter(status='pending').count(),
            'approved': cls.objects.filter(status='approved').count(),
            'disbursed': cls.objects.filter(status='disbursed').count(),
            'rejected': cls.objects.filter(status='rejected').count(),
            'total_amount': cls.objects.aggregate(total=Sum('amount'))['total'] or 0,
        }
        
        # Education level statistics
        education_stats = {}
        for code, name in cls.EDUCATION_LEVEL_CHOICES:
            education_stats[name] = cls.objects.filter(education_level=code).count()
        
        # Ward statistics
        ward_stats = {}
        for code, name in cls.WARD_CHOICES:
            ward_stats[name] = cls.objects.filter(ward=code).count()
        
        # SMS statistics
        sms_stats = {
            'sent': cls.objects.filter(sms_status='sent').count(),
            'failed': cls.objects.filter(sms_status='failed').count(),
            'not_sent': cls.objects.filter(sms_status='not_sent').count(),
            'partial': cls.objects.filter(sms_status='partial').count(),
        }
        
        # Sponsorship statistics - NEW
        sponsorship_stats = {
            'cdf': cls.objects.filter(sponsorship_source='cdf').count(),
            'mp': cls.objects.filter(sponsorship_source='mp').count(),
            'other': cls.objects.filter(sponsorship_source='other').count(),
            'total_sponsorship_amount': cls.objects.aggregate(
                total=Sum('sponsorship_amount')
            )['total'] or 0,
        }
        
        stats['education_stats'] = education_stats
        stats['ward_stats'] = ward_stats
        stats['sms_stats'] = sms_stats
        stats['sponsorship_stats'] = sponsorship_stats  # Added
        
        return stats
    
    def can_send_sms(self):
        """Check if SMS can be sent to this student"""
        if not self.phone and not self.guardian_phone:
            return False, "No phone number available"
        
        if self.status != 'approved':
            return False, "Student must be approved to send SMS"
        
        if self.sms_status == 'sent':
            return False, "SMS already sent"
        
        return True, "OK"
    
    def mark_sms_sent(self, user=None):
        """Mark SMS as sent"""
        self.sms_status = 'sent'
        self.sms_sent_at = timezone.now()
        if user:
            self.sms_sent_by = user
        self.save()
    
    def mark_sms_failed(self):
        """Mark SMS as failed"""
        self.sms_status = 'failed'
        self.save()
    
    def approve(self, user=None):
        """Approve student"""
        self.status = 'approved'
        self.date_processed = timezone.now()
        if user:
            self.updated_by = user
        self.save()
    
    def reject(self, reason, user=None):
        """Reject student"""
        self.status = 'rejected'
        self.date_processed = timezone.now()
        self.rejection_reason = reason
        if user:
            self.updated_by = user
        self.save()