# reports/admin.py
from django.contrib import admin
from .models import Report, ReportTemplate, ReportSchedule, ReportLog

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'report_type', 'status', 'generated_by', 'created_at', 'file_size_display')
    list_filter = ('report_type', 'status', 'format', 'created_at')
    search_fields = ('title', 'description', 'generated_by__username')
    readonly_fields = ('id', 'generation_started', 'generation_completed', 'processing_time')
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'report_type', 'description', 'status')
        }),
        ('File Information', {
            'fields': ('file', 'format', 'file_size')
        }),
        ('Generation Details', {
            'fields': ('generated_by', 'generation_started', 'generation_completed', 'processing_time')
        }),
        ('Filters and Parameters', {
            'fields': ('filters', 'parameters'),
            'classes': ('collapse',)
        }),
        ('Report Statistics', {
            'fields': ('total_students', 'total_amount', 'approved_count', 'pending_count', 'mp_sponsored_count'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'expires_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'default_format', 'is_active', 'created_by')
    list_filter = ('template_type', 'is_active')
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')

@admin.register(ReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'report_type', 'frequency', 'is_active', 'next_run')
    list_filter = ('report_type', 'frequency', 'is_active')
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'last_run', 'next_run', 'created_at', 'updated_at')

@admin.register(ReportLog)
class ReportLogAdmin(admin.ModelAdmin):
    list_display = ('report', 'level', 'message', 'timestamp')
    list_filter = ('level', 'timestamp')
    search_fields = ('message', 'report__title')
    readonly_fields = ('id', 'timestamp')
    
    def has_add_permission(self, request):
        return False