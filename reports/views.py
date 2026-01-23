# reports/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from django.db.models import Q, Sum, Count
import json
import uuid
from datetime import datetime, timedelta
import io
import csv
import os
import threading
import time
from django.core.files.base import ContentFile
from decimal import Decimal

from .models import Report, ReportTemplate, ReportSchedule, ReportLog
from .serializers import (
    ReportSerializer, ReportCreateSerializer, ReportUpdateSerializer,
    ReportTemplateSerializer, ReportScheduleSerializer, ReportLogSerializer
)
from students.models import Student

class ReportViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing reports
    """
    queryset = Report.objects.all().order_by('-created_at')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['report_type', 'status', 'format']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ReportCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ReportUpdateSerializer
        return ReportSerializer
    
    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        
        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date and end_date:
            queryset = queryset.filter(
                created_at__date__range=[start_date, end_date]
            )
        
        # For non-admin users, show only their reports
        if not user.is_staff:
            queryset = queryset.filter(generated_by=user)
        
        return queryset
    
    def perform_create(self, serializer):
        """Override create to add generated_by user"""
        report = serializer.save(generated_by=self.request.user)
        
        # Log the creation
        ReportLog.objects.create(
            report=report,
            level='info',
            message=f"Report '{report.title}' created by {self.request.user.username}",
            details={'action': 'create', 'user': self.request.user.username}
        )
        
        # Start async report generation
        self.start_report_generation(report.id)
    
    def start_report_generation(self, report_id):
        """Start report generation in a separate thread"""
        def generate_report():
            try:
                # Create a new instance for thread safety
                viewset = ReportViewSet()
                viewset.generate_report_sync(report_id)
            except Exception as e:
                print(f"Error generating report {report_id}: {e}")
                try:
                    report = Report.objects.get(id=report_id)
                    report.status = 'failed'
                    report.save()
                except:
                    pass
        
        thread = threading.Thread(target=generate_report)
        thread.daemon = True
        thread.start()
    
    def generate_report_sync(self, report_id):
        """Generate report synchronously"""
        try:
            report = Report.objects.get(id=report_id)
            report.status = 'processing'
            report.save()
            
            start_time = timezone.now()
            
            # Get filters
            filters = report.filters or {}
            year = filters.get('year', str(timezone.now().year))
            
            # Filter students based on report type and filters
            students_queryset = Student.objects.all()
            
            # Apply year filter if provided
            if year and year != 'all':
                try:
                    students_queryset = students_queryset.filter(date_applied__year=int(year))
                except (ValueError, TypeError):
                    # If year is not a valid integer or date_applied is None, skip filtering
                    pass
            
            # Apply other filters
            if filters.get('status') and filters['status'] != 'all':
                students_queryset = students_queryset.filter(status=filters['status'])
            
            if filters.get('ward') and filters['ward'] != 'all':
                students_queryset = students_queryset.filter(ward=filters['ward'])
            
            if filters.get('education_level') and filters['education_level'] != 'all':
                students_queryset = students_queryset.filter(education_level=filters['education_level'])
            
            if filters.get('sponsorship_source') and filters['sponsorship_source'] != 'all':
                students_queryset = students_queryset.filter(sponsorship_source=filters['sponsorship_source'])
            
            # Generate report based on type
            if report.report_type == 'student_allocation':
                file_content = self.generate_student_allocation_report(students_queryset, report)
            elif report.report_type == 'financial_summary':
                file_content = self.generate_financial_summary_report(students_queryset, report, year)
            elif report.report_type == 'ward_distribution':
                file_content = self.generate_ward_distribution_report(students_queryset, report, year)
            elif report.report_type == 'mp_sponsorship':
                file_content = self.generate_mp_sponsorship_report(students_queryset, report, year)
            else:
                file_content = self.generate_general_report(report)
            
            # Save file
            if report.format in ['csv', 'json', 'text'] and file_content:
                filename = f"{report.title.replace(' ', '_')}_{report.id}.{report.format}"
                report.file.save(filename, ContentFile(file_content))
                report.file_size = len(file_content)
            
            # Calculate statistics
            self.calculate_report_statistics(report, students_queryset)
            
            # Update report status
            report.status = 'completed'
            report.generation_completed = timezone.now()
            report.processing_time = (timezone.now() - start_time).seconds
            report.save()
            
            # Log success
            ReportLog.objects.create(
                report=report,
                level='info',
                message=f"Report '{report.title}' generated successfully",
                details={
                    'processing_time': report.processing_time,
                    'file_size': report.file_size,
                    'total_students': report.total_students,
                    'total_amount': float(report.total_amount)
                }
            )
            
        except Exception as e:
            print(f"Error in generate_report_sync: {e}")
            try:
                report = Report.objects.get(id=report_id)
                report.status = 'failed'
                report.save()
                
                ReportLog.objects.create(
                    report=report,
                    level='error',
                    message=f"Report generation failed: {str(e)}",
                    details={'error': str(e)}
                )
            except:
                pass
    
    def calculate_student_total_allocation(self, student):
        """Calculate total allocation for a single student"""
        sponsorship_amount = student.sponsorship_amount if student.sponsorship_amount else Decimal('0')
        return student.amount + sponsorship_amount
    
    def calculate_total_amount_for_queryset(self, students_queryset):
        """Calculate total amount for a queryset of students"""
        total_amount = Decimal('0')
        for student in students_queryset:
            total_amount += self.calculate_student_total_allocation(student)
        return total_amount
    
    def generate_student_allocation_report(self, students, report):
        """Generate student allocation report"""
        if report.format == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow([
                'Name', 'Registration No', 'Phone', 'Ward', 
                'Institution', 'Course', 'Education Level',
                'Status', 'Sponsorship Source', 'Sponsor Name',
                'CDF Amount', 'Sponsorship Amount', 'Total Amount',
                'Date Applied'
            ])
            
            # Write data
            for student in students:
                total_allocation = self.calculate_student_total_allocation(student)
                
                writer.writerow([
                    student.name,
                    student.registration_no,
                    student.phone or '',
                    student.ward,
                    student.institution,
                    student.course or '',
                    student.education_level,
                    student.status,
                    student.sponsorship_source,
                    student.sponsor_name or '',
                    float(student.amount),
                    float(student.sponsorship_amount or 0),
                    float(total_allocation),
                    student.date_applied.strftime('%Y-%m-%d') if student.date_applied else ''
                ])
            
            return output.getvalue().encode('utf-8')
        
        elif report.format == 'json':
            data = {
                'title': report.title,
                'generated_at': timezone.now().isoformat(),
                'total_students': students.count(),
                'students': []
            }
            
            for student in students:
                total_allocation = self.calculate_student_total_allocation(student)
                
                data['students'].append({
                    'name': student.name,
                    'registration_no': student.registration_no,
                    'phone': student.phone,
                    'ward': student.ward,
                    'institution': student.institution,
                    'course': student.course,
                    'education_level': student.education_level,
                    'status': student.status,
                    'sponsorship_source': student.sponsorship_source,
                    'sponsor_name': student.sponsor_name,
                    'amount': float(student.amount),
                    'sponsorship_amount': float(student.sponsorship_amount or 0),
                    'total_allocation': float(total_allocation),
                    'date_applied': student.date_applied.isoformat() if student.date_applied else None
                })
            
            return json.dumps(data, indent=2, default=str).encode('utf-8')
        
        else:  # text format
            output = []
            output.append(f"STUDENT ALLOCATION REPORT")
            output.append(f"Title: {report.title}")
            output.append(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
            output.append(f"Total Students: {students.count()}")
            output.append("=" * 80)
            output.append("")
            
            for student in students:
                total_allocation = self.calculate_student_total_allocation(student)
                
                output.append(f"{student.name} - {student.registration_no}")
                output.append(f"  Ward: {student.ward}")
                output.append(f"  Institution: {student.institution}")
                output.append(f"  Course: {student.course}")
                output.append(f"  Status: {student.status}")
                output.append(f"  Amount: KES {total_allocation:,.2f}")
                output.append("")
            
            return "\n".join(output).encode('utf-8')
    
    def generate_financial_summary_report(self, students, report, year):
        """Generate financial summary report"""
        # Calculate statistics
        total_students = students.count()
        total_amount = self.calculate_total_amount_for_queryset(students)
        avg_amount = total_amount / total_students if total_students > 0 else Decimal('0')
        
        if report.format == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            
            writer.writerow(['Year', 'Total Students', 'Total Amount (KES)', 'Average Amount (KES)'])
            writer.writerow([year, total_students, float(total_amount), float(avg_amount)])
            
            return output.getvalue().encode('utf-8')
        
        elif report.format == 'json':
            data = {
                'title': report.title,
                'year': year,
                'total_students': total_students,
                'total_amount': float(total_amount),
                'average_amount': float(avg_amount)
            }
            
            return json.dumps(data, indent=2).encode('utf-8')
        
        else:  # text format
            output = []
            output.append(f"FINANCIAL SUMMARY REPORT - {year}")
            output.append(f"Total Students: {total_students}")
            output.append(f"Total Amount: KES {total_amount:,.2f}")
            output.append(f"Average Amount: KES {avg_amount:,.2f}")
            
            return "\n".join(output).encode('utf-8')
    
    def generate_ward_distribution_report(self, students, report, year):
        """Generate ward distribution report"""
        # Group by ward and calculate manually
        ward_data = {}
        
        for student in students:
            ward = student.ward
            if ward not in ward_data:
                ward_data[ward] = {'count': 0, 'total_amount': Decimal('0')}
            
            ward_data[ward]['count'] += 1
            ward_data[ward]['total_amount'] += self.calculate_student_total_allocation(student)
        
        # Convert to list for output
        ward_stats = [
            {'ward': ward, 'count': data['count'], 'total': float(data['total_amount'])}
            for ward, data in ward_data.items()
        ]
        ward_stats.sort(key=lambda x: x['ward'])
        
        if report.format == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            
            writer.writerow(['Ward', 'Student Count', 'Total Amount (KES)'])
            for stat in ward_stats:
                writer.writerow([stat['ward'], stat['count'], stat['total']])
            
            return output.getvalue().encode('utf-8')
        
        elif report.format == 'json':
            data = {
                'title': report.title,
                'year': year,
                'wards': ward_stats
            }
            
            return json.dumps(data, indent=2, default=str).encode('utf-8')
        
        else:  # text format
            output = []
            output.append(f"WARD DISTRIBUTION REPORT - {year}")
            output.append("=" * 50)
            
            for stat in ward_stats:
                output.append(f"{stat['ward']}: {stat['count']} students, KES {stat['total']:,.2f}")
            
            return "\n".join(output).encode('utf-8')
    
    def generate_mp_sponsorship_report(self, students, report, year):
        """Generate MP sponsorship report"""
        mp_students = students.filter(sponsorship_source='mp')
        
        # Group by sponsor and calculate manually
        sponsor_data = {}
        
        for student in mp_students:
            sponsor_name = student.sponsor_name or 'Unknown'
            if sponsor_name not in sponsor_data:
                sponsor_data[sponsor_name] = {'count': 0, 'total_amount': Decimal('0')}
            
            sponsor_data[sponsor_name]['count'] += 1
            sponsor_data[sponsor_name]['total_amount'] += self.calculate_student_total_allocation(student)
        
        # Convert to list for output
        sponsors = [
            {'sponsor_name': sponsor, 'count': data['count'], 'total': float(data['total_amount'])}
            for sponsor, data in sponsor_data.items()
        ]
        sponsors.sort(key=lambda x: x['sponsor_name'])
        
        if report.format == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            
            writer.writerow(['Sponsor Name', 'Student Count', 'Total Amount (KES)'])
            for sponsor in sponsors:
                writer.writerow([sponsor['sponsor_name'], sponsor['count'], sponsor['total']])
            
            return output.getvalue().encode('utf-8')
        
        elif report.format == 'json':
            data = {
                'title': report.title,
                'year': year,
                'total_mp_students': mp_students.count(),
                'sponsors': sponsors
            }
            
            return json.dumps(data, indent=2, default=str).encode('utf-8')
        
        else:  # text format
            output = []
            output.append(f"MP SPONSORSHIP REPORT - {year}")
            output.append(f"Total MP Sponsored Students: {mp_students.count()}")
            output.append("=" * 50)
            
            for sponsor in sponsors:
                output.append(f"{sponsor['sponsor_name']}: {sponsor['count']} students, KES {sponsor['total']:,.2f}")
            
            return "\n".join(output).encode('utf-8')
    
    def generate_general_report(self, report):
        """Generate a general report"""
        content = f"Report: {report.title}\nType: {report.report_type}\nGenerated: {timezone.now()}"
        return content.encode('utf-8')
    
    def calculate_report_statistics(self, report, students):
        """Calculate report statistics"""
        report.total_students = students.count()
        report.total_amount = self.calculate_total_amount_for_queryset(students)
        report.approved_count = students.filter(status='approved').count()
        report.pending_count = students.filter(status='pending').count()
        report.mp_sponsored_count = students.filter(sponsorship_source='mp').count()
        report.save()
    
    @action(detail=True, methods=['post'])
    def regenerate(self, request, pk=None):
        """Regenerate a report"""
        report = self.get_object()
        
        # Store old status for logging
        old_status = report.status
        
        # Reset status
        report.status = 'pending'
        report.save()
        
        # Log the regeneration
        ReportLog.objects.create(
            report=report,
            level='info',
            message=f"Report regeneration started by {request.user.username}",
            details={'action': 'regenerate', 'user': request.user.username, 'old_status': old_status}
        )
        
        # Start regeneration
        self.start_report_generation(report.id)
        
        return Response({
            'message': 'Report regeneration started',
            'report_id': str(report.id)
        })
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download a report file"""
        report = self.get_object()
        
        if not report.file:
            return Response(
                {'error': 'Report file not available. Please regenerate the report.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        response = FileResponse(report.file.open('rb'))
        response['Content-Disposition'] = f'attachment; filename="{report.title}.{report.format}"'
        
        # Log download
        ReportLog.objects.create(
            report=report,
            level='info',
            message=f"Report downloaded by {request.user.username}",
            details={'action': 'download', 'user': request.user.username}
        )
        
        return response
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get report statistics"""
        user = request.user
        
        if user.is_staff:
            reports = Report.objects.all()
        else:
            reports = Report.objects.filter(generated_by=user)
        
        total_reports = reports.count()
        this_month = reports.filter(
            created_at__month=timezone.now().month,
            created_at__year=timezone.now().year
        ).count()
        
        completed = reports.filter(status='completed').count()
        pending = reports.filter(status='pending').count()
        success_rate = (completed / total_reports * 100) if total_reports > 0 else 0
        
        # Calculate total storage used
        total_storage = reports.aggregate(total=Sum('file_size'))['total'] or 0
        total_storage_mb = total_storage / (1024 * 1024)  # Convert to MB
        
        return Response({
            'total_reports': total_reports,
            'this_month': this_month,
            'pending_reports': pending,
            'success_rate': round(success_rate, 1),
            'total_storage': round(total_storage_mb, 2),
            'storage_usage': {
                'used_gb': round(total_storage_mb / 1024, 2),
                'available_gb': 10,
                'percentage': min(round((total_storage_mb / (10 * 1024)) * 100, 1), 100)
            }
        })
    
    @action(detail=False, methods=['get'])
    def report_types(self, request):
        """Get available report types"""
        return Response([
            {'value': 'student_allocation', 'label': 'Student Allocation'},
            {'value': 'financial_summary', 'label': 'Financial Summary'},
            {'value': 'ward_distribution', 'label': 'Ward Distribution'},
            {'value': 'mp_sponsorship', 'label': 'MP Sponsorship'},
            {'value': 'performance', 'label': 'Performance Analytics'},
            {'value': 'compliance', 'label': 'Compliance Reports'},
            {'value': 'custom', 'label': 'Custom Report'}
        ])
    
    @action(detail=False, methods=['get'])
    def report_filters(self, request):
        """Get available report filters"""
        try:
            # Get distinct values from students
            years = Student.objects.dates('date_applied', 'year').distinct()
            wards = Student.objects.values_list('ward', flat=True).distinct()
            education_levels = Student.objects.values_list('education_level', flat=True).distinct()
            statuses = Student.objects.values_list('status', flat=True).distinct()
            sponsorship_sources = Student.objects.values_list('sponsorship_source', flat=True).distinct()
            
            return Response({
                'years': [str(year.year) for year in years] if years else [str(timezone.now().year)],
                'wards': list(filter(None, wards)) or ['Nyangores', 'Sigor', 'Chebunyo', 'Siongiroi', 'Kongasis'],
                'education_levels': list(filter(None, education_levels)) or ['Secondary', 'University', 'College', 'TVET'],
                'statuses': list(filter(None, statuses)) or ['approved', 'pending', 'rejected'],
                'sponsorship_sources': list(filter(None, sponsorship_sources)) or ['cdf', 'mp', 'other']
            })
        except Exception as e:
            print(f"Error fetching filters: {e}")
            return Response({
                'years': ['2024', '2023', '2022', '2021'],
                'wards': ['Nyangores', 'Sigor', 'Chebunyo', 'Siongiroi', 'Kongasis'],
                'education_levels': ['Secondary', 'University', 'College', 'TVET'],
                'statuses': ['approved', 'pending', 'rejected'],
                'sponsorship_sources': ['cdf', 'mp', 'other']
            })
    
    @action(detail=False, methods=['post'])
    def quick_report(self, request):
        """Generate a quick report"""
        try:
            data = request.data
            report_type = data.get('report_type', 'student_allocation')
            format_type = data.get('format', 'csv')
            
            # Create report
            report = Report.objects.create(
                title=f"Quick {report_type.replace('_', ' ').title()}",
                report_type=report_type,
                description=f"Quick {report_type} report generated at {timezone.now()}",
                format=format_type,
                status='pending',
                generated_by=request.user,
                filters=data.get('filters', {})
            )
            
            # Log the creation
            ReportLog.objects.create(
                report=report,
                level='info',
                message=f"Quick report '{report.title}' created by {request.user.username}",
                details={'action': 'quick_create', 'user': request.user.username}
            )
            
            # Now start generation
            self.start_report_generation(report.id)
            
            return Response(ReportSerializer(report, context={'request': request}).data)
            
        except Exception as e:
            print(f"Error in quick_report action: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """Bulk delete reports"""
        try:
            report_ids = request.data.get('report_ids', [])
            
            if not report_ids:
                return Response({'error': 'No report IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Filter by user permissions
            user = request.user
            if user.is_staff:
                reports_to_delete = Report.objects.filter(id__in=report_ids)
            else:
                reports_to_delete = Report.objects.filter(id__in=report_ids, generated_by=user)
            
            count = reports_to_delete.count()
            reports_to_delete.delete()
            
            return Response({'message': f'Successfully deleted {count} reports'})
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReportTemplateViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing report templates
    """
    queryset = ReportTemplate.objects.filter(is_active=True)
    serializer_class = ReportTemplateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return super().get_permissions()


class ReportScheduleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing report schedules
    """
    queryset = ReportSchedule.objects.filter(is_active=True)
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ReportLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing report logs
    """
    serializer_class = ReportLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['level', 'report']
    
    def get_queryset(self):
        user = self.request.user
        queryset = ReportLog.objects.all()
        
        if not user.is_staff:
            # Show logs only for user's reports
            user_reports = Report.objects.filter(generated_by=user)
            queryset = queryset.filter(report__in=user_reports)
        
        return queryset


# Function-based views (for backward compatibility)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_types_view(request):
    return Response([
        {'value': 'student_allocation', 'label': 'Student Allocation Report'},
        {'value': 'financial_summary', 'label': 'Financial Summary Report'},
        {'value': 'ward_distribution', 'label': 'Ward Distribution Report'},
        {'value': 'mp_sponsorship', 'label': 'MP Sponsorship Report'},
        {'value': 'performance', 'label': 'Performance Analytics'},
        {'value': 'compliance', 'label': 'Compliance Report'},
        {'value': 'custom', 'label': 'Custom Report'},
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_filters_view(request):
    try:
        years = Student.objects.dates('date_applied', 'year').distinct()
        wards = Student.objects.values_list('ward', flat=True).distinct()
        education_levels = Student.objects.values_list('education_level', flat=True).distinct()
        statuses = Student.objects.values_list('status', flat=True).distinct()
        sponsorship_sources = Student.objects.values_list('sponsorship_source', flat=True).distinct()
        
        return Response({
            'years': [str(year.year) for year in years] if years else [str(timezone.now().year)],
            'wards': list(filter(None, wards)) or ['Nyangores', 'Sigor', 'Chebunyo', 'Siongiroi', 'Kongasis'],
            'education_levels': list(filter(None, education_levels)) or ['Secondary', 'University', 'College', 'TVET'],
            'statuses': list(filter(None, statuses)) or ['approved', 'pending', 'rejected'],
            'sponsorship_sources': list(filter(None, sponsorship_sources)) or ['cdf', 'mp', 'other']
        })
    except Exception as e:
        print(f"Error fetching filters: {e}")
        return Response({
            'years': ['2024', '2023', '2022', '2021'],
            'wards': ['Nyangores', 'Sigor', 'Chebunyo', 'Siongiroi', 'Kongasis'],
            'education_levels': ['Secondary', 'University', 'College', 'TVET'],
            'statuses': ['approved', 'pending', 'rejected'],
            'sponsorship_sources': ['cdf', 'mp', 'other']
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_quick_report_view(request):
    """Generate quick report - FIXED VERSION"""
    try:
        data = request.data
        report_type = data.get('report_type', 'student_allocation')
        format_type = data.get('format', 'csv')
        filters = data.get('filters', {})
        
        # Create report using the Report model directly
        report = Report.objects.create(
            title=f"Quick {report_type.replace('_', ' ').title()}",
            report_type=report_type,
            description=f"Quick {report_type} report generated at {timezone.now()}",
            format=format_type,
            status='pending',
            generated_by=request.user,
            filters=filters
        )
        
        # Log the creation
        ReportLog.objects.create(
            report=report,
            level='info',
            message=f"Quick report '{report.title}' created by {request.user.username}",
            details={'action': 'quick_create', 'user': request.user.username, 'filters': filters}
        )
        
        # Start report generation in background thread
        def generate_report_background(report_id):
            try:
                time.sleep(1)  # Small delay
                # Create a new viewset instance for thread safety
                viewset = ReportViewSet()
                viewset.generate_report_sync(report_id)
            except Exception as e:
                print(f"Error in quick report background generation: {e}")
                try:
                    report = Report.objects.get(id=report_id)
                    report.status = 'failed'
                    report.save()
                except:
                    pass
        
        # Start generation in background thread
        thread = threading.Thread(target=generate_report_background, args=(report.id,))
        thread.daemon = True
        thread.start()
        
        # Return the serialized report
        return Response(ReportSerializer(report, context={'request': request}).data)
        
    except Exception as e:
        print(f"Error in generate_quick_report_view: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_delete_reports_view(request):
    """Bulk delete reports"""
    try:
        report_ids = request.data.get('report_ids', [])
        
        if not report_ids:
            return Response({'error': 'No report IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Filter by user permissions
        user = request.user
        if user.is_staff:
            reports_to_delete = Report.objects.filter(id__in=report_ids)
        else:
            reports_to_delete = Report.objects.filter(id__in=report_ids, generated_by=user)
        
        count = reports_to_delete.count()
        reports_to_delete.delete()
        
        return Response({'message': f'Successfully deleted {count} reports'})
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)