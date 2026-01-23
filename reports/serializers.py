# reports/serializers.py
from rest_framework import serializers
from .models import Report, ReportTemplate, ReportSchedule, ReportLog
from django.contrib.auth import get_user_model

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']

class ReportLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportLog
        fields = ['id', 'level', 'message', 'details', 'timestamp']
        read_only_fields = ['timestamp']

class ReportSerializer(serializers.ModelSerializer):
    generated_by = UserSerializer(read_only=True)
    file_size_display = serializers.SerializerMethodField()
    logs = ReportLogSerializer(many=True, read_only=True)
    
    class Meta:
        model = Report
        fields = [
            'id', 'title', 'report_type', 'description', 'status',
            'format', 'file', 'file_size', 'file_size_display',
            'filters', 'parameters',
            'generated_by', 'generation_started', 'generation_completed',
            'processing_time', 'total_students', 'total_amount',
            'approved_count', 'pending_count', 'mp_sponsored_count',
            'scheduled_at', 'is_scheduled', 'recurrence',
            'created_at', 'updated_at', 'expires_at', 'logs'
        ]
        read_only_fields = [
            'id', 'status', 'file_size', 'generated_by', 
            'generation_started', 'generation_completed',
            'processing_time', 'total_students', 'total_amount',
            'approved_count', 'pending_count', 'mp_sponsored_count',
            'created_at', 'updated_at'
        ]
    
    def get_file_size_display(self, obj):
        return obj.file_size_display

class ReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = [
            'title', 'report_type', 'description',
            'format', 'filters', 'parameters',
            'scheduled_at', 'is_scheduled', 'recurrence',
            'expires_at'
        ]
    
    def validate_filters(self, value):
        """Validate filters JSON"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Filters must be a JSON object")
        return value
    
    def validate_parameters(self, value):
        """Validate parameters JSON"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Parameters must be a JSON object")
        return value

class ReportUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ['title', 'description', 'expires_at']

class ReportTemplateSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    
    class Meta:
        model = ReportTemplate
        fields = [
            'id', 'name', 'template_type', 'description',
            'template_file', 'header_html', 'footer_html', 'css_styles',
            'default_format', 'include_logo', 'include_charts', 'include_summary',
            'is_active', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

class ReportScheduleSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    
    class Meta:
        model = ReportSchedule
        fields = [
            'id', 'name', 'description', 'report_type', 'frequency',
            'day_of_week', 'day_of_month', 'scheduled_time',
            'start_date', 'end_date', 'last_run', 'next_run',
            'email_recipients', 'is_active', 'keep_last_n',
            'auto_delete_old', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'last_run', 'next_run', 'created_by', 'created_at', 'updated_at']