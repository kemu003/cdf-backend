from django.db import models
from django.conf import settings  # Add this import
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
from django.utils import timezone
from datetime import datetime, timedelta

# Remove this line: from django.contrib.auth.models import User
# Use settings.AUTH_USER_MODEL instead

class Report(models.Model):
    REPORT_TYPES = [
        ('student_allocation', 'Student Allocation Report'),
        ('financial_summary', 'Financial Summary Report'),
        ('ward_distribution', 'Ward Distribution Report'),
        ('mp_sponsorship', 'MP Sponsorship Report'),
        ('performance', 'Performance Analytics'),
        ('compliance', 'Compliance Report'),
        ('custom', 'Custom Report'),
    ]
    
    REPORT_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    REPORT_FORMATS = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
        ('json', 'JSON'),
        ('text', 'Text'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPES)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=REPORT_STATUS, default='pending')
    format = models.CharField(max_length=10, choices=REPORT_FORMATS, default='csv')
    
    # File storage
    file = models.FileField(upload_to='reports/%Y/%m/%d/', blank=True, null=True)
    file_size = models.IntegerField(default=0)  # in bytes
    file_path = models.CharField(max_length=500, blank=True, null=True)
    
    # Filters and parameters (stored as JSON)
    filters = models.JSONField(default=dict, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    
    # Generation details - FIXED: Use settings.AUTH_USER_MODEL
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='reports')
    generation_started = models.DateTimeField(auto_now_add=True)
    generation_completed = models.DateTimeField(null=True, blank=True)
    processing_time = models.IntegerField(default=0)  # in seconds
    
    # Report data
    total_students = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    approved_count = models.IntegerField(default=0)
    pending_count = models.IntegerField(default=0)
    mp_sponsored_count = models.IntegerField(default=0)
    
    # Schedule
    scheduled_at = models.DateTimeField(null=True, blank=True)
    is_scheduled = models.BooleanField(default=False)
    recurrence = models.CharField(max_length=50, blank=True, null=True)  # daily, weekly, monthly
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'report_type']),
            models.Index(fields=['generated_by', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.get_report_type_display()}"
    
    @property
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    @property
    def file_size_display(self):
        """Convert file size to human readable format"""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        elif self.file_size < 1024 * 1024 * 1024:
            return f"{self.file_size / (1024 * 1024):.1f} MB"
        else:
            return f"{self.file_size / (1024 * 1024 * 1024):.1f} GB"
    
    def save(self, *args, **kwargs):
        if self.status == 'completed' and not self.generation_completed:
            self.generation_completed = timezone.now()
        super().save(*args, **kwargs)

class ReportTemplate(models.Model):
    TEMPLATE_TYPES = [
        ('student', 'Student Report Template'),
        ('financial', 'Financial Report Template'),
        ('ward', 'Ward Report Template'),
        ('mp', 'MP Sponsorship Template'),
        ('standard', 'Standard Template'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPES)
    description = models.TextField(blank=True, null=True)
    
    # Template configuration
    template_file = models.FileField(upload_to='report_templates/', blank=True, null=True)
    header_html = models.TextField(blank=True, null=True)
    footer_html = models.TextField(blank=True, null=True)
    css_styles = models.TextField(blank=True, null=True)
    
    # Default settings
    default_format = models.CharField(max_length=10, choices=Report.REPORT_FORMATS, default='csv')
    include_logo = models.BooleanField(default=True)
    include_charts = models.BooleanField(default=True)
    include_summary = models.BooleanField(default=True)
    
    # Metadata
    is_active = models.BooleanField(default=True)
    # FIXED: Use settings.AUTH_USER_MODEL
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name

class ReportSchedule(models.Model):
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]
    
    DAY_CHOICES = [
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    
    # Schedule configuration
    report_type = models.CharField(max_length=50, choices=Report.REPORT_TYPES)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    day_of_week = models.CharField(max_length=10, choices=DAY_CHOICES, blank=True, null=True)
    day_of_month = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(31)], null=True, blank=True)
    
    # Time settings
    scheduled_time = models.TimeField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    
    # Recipients
    email_recipients = models.JSONField(default=list, blank=True)
    
    # Settings
    is_active = models.BooleanField(default=True)
    keep_last_n = models.IntegerField(default=10)  # Keep last N reports
    auto_delete_old = models.BooleanField(default=True)
    
    # Metadata
    # FIXED: Use settings.AUTH_USER_MODEL
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['next_run']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # Calculate next run date (simplified version without dateutil)
        if not self.next_run:
            now = timezone.now()
            scheduled_datetime = datetime.combine(self.start_date, self.scheduled_time)
            scheduled_datetime = timezone.make_aware(scheduled_datetime)
            
            if scheduled_datetime < now:
                # Schedule has already passed, calculate next occurrence
                if self.frequency == 'daily':
                    self.next_run = now + timedelta(days=1)
                elif self.frequency == 'weekly':
                    self.next_run = now + timedelta(weeks=1)
                elif self.frequency == 'monthly':
                    # Simple monthly calculation
                    month = now.month + 1
                    year = now.year
                    if month > 12:
                        month = 1
                        year += 1
                    self.next_run = datetime(year, month, now.day, self.scheduled_time.hour, self.scheduled_time.minute)
                    self.next_run = timezone.make_aware(self.next_run)
                elif self.frequency == 'quarterly':
                    self.next_run = now + timedelta(days=91)  # Approximate quarter
                elif self.frequency == 'yearly':
                    self.next_run = now + timedelta(days=365)
            else:
                self.next_run = scheduled_datetime
        
        super().save(*args, **kwargs)

class ReportLog(models.Model):
    LOG_LEVELS = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('debug', 'Debug'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='logs', null=True, blank=True)
    level = models.CharField(max_length=10, choices=LOG_LEVELS, default='info')
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['report', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.get_level_display()} - {self.message[:50]}"