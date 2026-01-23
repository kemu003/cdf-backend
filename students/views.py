# students/views.py - Update the SMS sending methods
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
from django.utils import timezone
import csv
import logging

from .models import Student
from .serializers import StudentSerializer
from .permissions import IsAdminOrCommittee
from .filters import StudentFilter
from .sms import send_sms_notification, get_sms_balance

logger = logging.getLogger(__name__)

class StudentViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing students
    Only accessible by admin or committee members
    """
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated, IsAdminOrCommittee]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = StudentFilter
    search_fields = ['name', 'registration_no', 'institution', 'phone', 'guardian_phone']
    ordering_fields = ['name', 'date_applied', 'amount', 'status']
    ordering = ['-date_applied']
    
    def get_queryset(self):
        # Filter by status if provided
        status_param = self.request.query_params.get('status', None)
        if status_param:
            return self.queryset.filter(status=status_param)
        return self.queryset
    
    def _generate_sms_message(self, student, custom_message=None):
        """
        Generate SMS message based on sponsorship source
        """
        if custom_message:
            return custom_message
        
        # Get the total allocation (CDF + sponsorship)
        total_allocation = student.total_allocation
        
        # Generate message based on sponsorship source
        if student.sponsorship_source == 'cdf':
            message = f"Dear {student.name}, you have been awarded KES {student.amount:,.2f} CDF bursary for your studies at {student.institution}. Congratulations! - Chepalungu CDF"
        
        elif student.sponsorship_source == 'mp':
            sponsor_name = student.sponsor_name if student.sponsor_name else "your MP"
            
            if student.amount > 0 and student.sponsorship_amount and student.sponsorship_amount > 0:
                message = f"Dear {student.name}, you have been awarded KES {student.amount:,.2f} from CDF and KES {student.sponsorship_amount:,.2f} from {sponsor_name} for your studies at {student.institution}. Total: KES {total_allocation:,.2f}. Congratulations! - Chepalungu CDF"
            elif student.sponsorship_amount and student.sponsorship_amount > 0:
                message = f"Dear {student.name}, you have been awarded KES {student.sponsorship_amount:,.2f} from {sponsor_name} for your studies at {student.institution}. Congratulations! - Chepalungu CDF"
            else:
                message = f"Dear {student.name}, you have been awarded KES {student.amount:,.2f} CDF bursary for your studies at {student.institution}. Congratulations! - Chepalungu CDF"
        
        elif student.sponsorship_source == 'other':
            sponsor_name = student.sponsor_name if student.sponsor_name else "your sponsor"
            
            if student.amount > 0 and student.sponsorship_amount and student.sponsorship_amount > 0:
                message = f"Dear {student.name}, you have been awarded KES {student.amount:,.2f} from CDF and KES {student.sponsorship_amount:,.2f} from {sponsor_name} for your studies at {student.institution}. Total: KES {total_allocation:,.2f}. Congratulations! - Chepalungu CDF"
            elif student.sponsorship_amount and student.sponsorship_amount > 0:
                message = f"Dear {student.name}, you have been awarded KES {student.sponsorship_amount:,.2f} from {sponsor_name} for your studies at {student.institution}. Congratulations! - Chepalungu CDF"
            else:
                message = f"Dear {student.name}, you have been awarded KES {student.amount:,.2f} CDF bursary for your studies at {student.institution}. Congratulations! - Chepalungu CDF"
        
        else:
            # Default fallback
            message = f"Dear {student.name}, you have been awarded KES {student.amount:,.2f} bursary for your studies at {student.institution}. Congratulations! - Chepalungu CDF"
        
        return message
    
    @action(detail=True, methods=['put'])
    def approve(self, request, pk=None):
        """
        Approve a student allocation
        """
        student = self.get_object()
        
        if student.status == 'approved':
            return Response(
                {"detail": "Student is already approved."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student.status = 'approved'
        student.date_processed = timezone.now()
        student.updated_by = request.user
        student.save()
        
        serializer = self.get_serializer(student)
        return Response(serializer.data)
    
    @action(detail=True, methods=['put'])
    def reject(self, request, pk=None):
        """
        Reject a student allocation
        """
        student = self.get_object()
        reason = request.data.get('reason', '')
        
        if not reason:
            return Response(
                {"reason": "Rejection reason is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student.status = 'rejected'
        student.date_processed = timezone.now()
        student.rejection_reason = reason
        student.updated_by = request.user
        student.save()
        
        serializer = self.get_serializer(student)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def send_sms(self, request, pk=None):
        """
        Send SMS notification to student
        Sends to both student and guardian phones when available
        """
        student = self.get_object()
        
        # Check if student has any phone number
        if not student.phone and not student.guardian_phone:
            return Response(
                {'error': 'No phone number available for this student'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if student is approved
        if student.status != 'approved' and student.status != 'disbursed':
            return Response(
                {'error': 'Student must be approved to send SMS'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine which phone numbers to send to
        phones_to_send = []
        
        if student.phone:
            phones_to_send.append(('student', student.phone))
        
        if student.guardian_phone:
            phones_to_send.append(('guardian', student.guardian_phone))
        
        # Remove duplicates (in case phone and guardian_phone are the same)
        unique_phones = {}
        for phone_type, phone_number in phones_to_send:
            if phone_number not in unique_phones:
                unique_phones[phone_number] = phone_type
            else:
                # If already exists, update type to include both
                existing_type = unique_phones[phone_number]
                if phone_type not in existing_type:
                    unique_phones[phone_number] = f"{existing_type}/{phone_type}"
        
        # Create the message based on sponsorship source
        custom_message = request.data.get('message')
        message = self._generate_sms_message(student, custom_message)
        
        results = []
        success_count = 0
        failure_count = 0
        
        # Send SMS to each unique phone number
        for phone_number, phone_type in unique_phones.items():
            logger.info(f"Sending SMS to {phone_type} phone: {phone_number} for student {student.id}")
            
            try:
                success, details = send_sms_notification(
                    phone_number, 
                    message, 
                    student_id=student.id
                )
                
                if success:
                    results.append({
                        'phone': phone_number,
                        'type': phone_type,
                        'status': 'success',
                        'details': details
                    })
                    success_count += 1
                else:
                    results.append({
                        'phone': phone_number,
                        'type': phone_type,
                        'status': 'failed',
                        'error': details
                    })
                    failure_count += 1
                    
            except Exception as e:
                logger.error(f"Error sending SMS to {phone_number}: {str(e)}")
                results.append({
                    'phone': phone_number,
                    'type': phone_type,
                    'status': 'failed',
                    'error': str(e)
                })
                failure_count += 1
        
        # Update student SMS status based on results
        if success_count > 0:
            if failure_count == 0:
                student.sms_status = 'sent'
            else:
                student.sms_status = 'partial'
        else:
            student.sms_status = 'failed'
        
        # If at least one SMS was sent successfully, mark as disbursed
        if success_count > 0 and student.status == 'approved':
            student.status = 'disbursed'
        
        student.sms_sent_at = timezone.now()
        student.sms_sent_by = request.user
        student.save()
        
        # Prepare response
        if success_count > 0:
            response_data = {
                "success": True,
                "message": f"SMS sent to {success_count} phone(s). {failure_count} failed.",
                "student_id": student.id,
                "student_name": student.name,
                "total_phones": len(unique_phones),
                "success_count": success_count,
                "failure_count": failure_count,
                "sms_message": message,
                "sponsorship_source": student.sponsorship_source,
                "total_amount": float(student.total_allocation),
                "results": results,
                "sms_status": student.sms_status,
                "student_status": student.status
            }
            
            if failure_count > 0:
                return Response(response_data, status=status.HTTP_207_MULTI_STATUS)
            else:
                return Response(response_data)
        else:
            return Response({
                "success": False,
                "error": "Failed to send SMS to any phone number",
                "student_id": student.id,
                "student_name": student.name,
                "results": results,
                "sms_status": student.sms_status
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def bulk_send_sms(self, request):
        """
        Send SMS to multiple approved students
        Sends to both student and guardian phones when available
        """
        try:
            # Get student IDs from request
            student_ids = request.data.get('student_ids', [])
            custom_message = request.data.get('message', '')
            
            if not student_ids:
                return Response(
                    {"detail": "No student IDs provided."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get approved students
            students = self.get_queryset().filter(
                id__in=student_ids,
                status__in=['approved', 'disbursed']
            )
            
            if not students.exists():
                return Response({
                    "success": False,
                    "message": "No approved students found with the provided IDs."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            overall_success = 0
            overall_failure = 0
            student_results = []
            
            # Group students by sponsorship source for summary
            sponsorship_summary = {
                'cdf': {'total': 0, 'success': 0, 'failed': 0},
                'mp': {'total': 0, 'success': 0, 'failed': 0},
                'other': {'total': 0, 'success': 0, 'failed': 0}
            }
            
            for student in students:
                # Update sponsorship summary counts
                sponsorship_summary[student.sponsorship_source]['total'] += 1
                
                student_phones_sent = 0
                student_phones_failed = 0
                phone_results = []
                
                # Determine which phone numbers to send to
                phones_to_send = []
                
                if student.phone:
                    phones_to_send.append(('student', student.phone))
                
                if student.guardian_phone:
                    phones_to_send.append(('guardian', student.guardian_phone))
                
                # Remove duplicates
                unique_phones = {}
                for phone_type, phone_number in phones_to_send:
                    if phone_number not in unique_phones:
                        unique_phones[phone_number] = phone_type
                    else:
                        existing_type = unique_phones[phone_number]
                        if phone_type not in existing_type:
                            unique_phones[phone_number] = f"{existing_type}/{phone_type}"
                
                # Skip if no phones
                if not unique_phones:
                    student_results.append({
                        'student_id': student.id,
                        'name': student.name,
                        'registration_no': student.registration_no,
                        'sponsorship_source': student.sponsorship_source,
                        'status': 'failed',
                        'error': 'No phone numbers available',
                        'phones_sent': 0,
                        'phones_failed': 0
                    })
                    sponsorship_summary[student.sponsorship_source]['failed'] += 1
                    overall_failure += 1
                    continue
                
                # Create message for this student based on sponsorship
                message = custom_message or self._generate_sms_message(student)
                
                # Send SMS to each unique phone number
                for phone_number, phone_type in unique_phones.items():
                    try:
                        success, details = send_sms_notification(
                            phone_number, 
                            message, 
                            student_id=student.id
                        )
                        
                        if success:
                            phone_results.append({
                                'phone': phone_number,
                                'type': phone_type,
                                'status': 'success'
                            })
                            student_phones_sent += 1
                        else:
                            phone_results.append({
                                'phone': phone_number,
                                'type': phone_type,
                                'status': 'failed',
                                'error': details
                            })
                            student_phones_failed += 1
                            
                    except Exception as e:
                        logger.error(f"Error sending SMS to student {student.id}: {str(e)}")
                        phone_results.append({
                            'phone': phone_number,
                            'type': phone_type,
                            'status': 'failed',
                            'error': str(e)
                        })
                        student_phones_failed += 1
                
                # Update student status based on results
                if student_phones_sent > 0:
                    if student_phones_failed == 0:
                        student.sms_status = 'sent'
                    else:
                        student.sms_status = 'partial'
                    
                    # Mark as disbursed if SMS sent successfully
                    if student.status == 'approved':
                        student.status = 'disbursed'
                    
                    sponsorship_summary[student.sponsorship_source]['success'] += 1
                    overall_success += 1
                else:
                    student.sms_status = 'failed'
                    sponsorship_summary[student.sponsorship_source]['failed'] += 1
                    overall_failure += 1
                
                student.sms_sent_at = timezone.now()
                student.sms_sent_by = request.user
                student.save()
                
                # Add to student results
                student_results.append({
                    'student_id': student.id,
                    'name': student.name,
                    'registration_no': student.registration_no,
                    'sponsorship_source': student.sponsorship_source,
                    'sponsor_name': student.sponsor_name,
                    'total_amount': float(student.total_allocation),
                    'status': 'sent' if student_phones_sent > 0 else 'failed',
                    'sms_message': message,
                    'phones_sent': student_phones_sent,
                    'phones_failed': student_phones_failed,
                    'phone_results': phone_results,
                    'student_status': student.status
                })
            
            # Clean up sponsorship summary (remove empty entries)
            sponsorship_summary = {k: v for k, v in sponsorship_summary.items() if v['total'] > 0}
            
            return Response({
                "success": True,
                "message": f"Bulk SMS operation completed. Success: {overall_success}, Failed: {overall_failure}",
                "total_students": len(student_ids),
                "processed_students": students.count(),
                "success_count": overall_success,
                "failure_count": overall_failure,
                "sponsorship_summary": sponsorship_summary,
                "results": student_results
            })
            
        except Exception as e:
            logger.error(f"Error in bulk_send_sms: {str(e)}")
            return Response(
                {"detail": f"Internal server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def sms_balance(self, request):
        """
        Get SMS balance from provider
        """
        try:
            balance = get_sms_balance()
            
            return Response({
                "success": True,
                "balance": balance,
            })
                
        except Exception as e:
            logger.error(f"Error getting SMS balance: {str(e)}")
            return Response(
                {"detail": f"Internal server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """
        Export students data to CSV including sponsorship information
        """
        students = self.filter_queryset(self.get_queryset())
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="students-{timezone.now().date()}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Name', 'Registration No', 'Phone', 'Guardian Phone',
            'Education Level', 'Institution', 'Course', 'Year', 'Ward',
            'CDF Amount', 'Sponsorship Source', 'Sponsor Name', 'Sponsorship Date',
            'Sponsorship Amount', 'Total Allocation', 'Status', 'SMS Status',
            'Date Applied', 'Date Processed', 'SMS Sent At'
        ])
        
        for student in students:
            writer.writerow([
                student.id,
                student.name,
                student.registration_no,
                student.phone or '',
                student.guardian_phone,
                student.get_education_level_display(),
                student.institution,
                student.course,
                student.year,
                student.ward,
                student.amount,
                student.get_sponsorship_source_display(),
                student.sponsor_name or '',
                student.sponsorship_date.strftime('%Y-%m-%d') if student.sponsorship_date else '',
                student.sponsorship_amount or '',
                student.total_allocation,
                student.get_status_display(),
                student.get_sms_status_display(),
                student.date_applied.strftime('%Y-%m-%d %H:%M:%S'),
                student.date_processed.strftime('%Y-%m-%d %H:%M:%S') if student.date_processed else '',
                student.sms_sent_at.strftime('%Y-%m-%d %H:%M:%S') if student.sms_sent_at else ''
            ])
        
        return response
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get student statistics including sponsorship information
        """
        stats = Student.get_statistics()
        
        # Add sponsorship breakdown
        sponsorship_breakdown = {
            'cdf': {
                'count': Student.objects.filter(sponsorship_source='cdf').count(),
                'total_amount': Student.objects.filter(sponsorship_source='cdf').aggregate(
                    total=models.Sum('amount')
                )['total'] or 0,
                'total_sponsorship': 0,
            },
            'mp': {
                'count': Student.objects.filter(sponsorship_source='mp').count(),
                'total_amount': Student.objects.filter(sponsorship_source='mp').aggregate(
                    total=models.Sum('amount')
                )['total'] or 0,
                'total_sponsorship': Student.objects.filter(sponsorship_source='mp').aggregate(
                    total=models.Sum('sponsorship_amount')
                )['total'] or 0,
            },
            'other': {
                'count': Student.objects.filter(sponsorship_source='other').count(),
                'total_amount': Student.objects.filter(sponsorship_source='other').aggregate(
                    total=models.Sum('amount')
                )['total'] or 0,
                'total_sponsorship': Student.objects.filter(sponsorship_source='other').aggregate(
                    total=models.Sum('sponsorship_amount')
                )['total'] or 0,
            }
        }
        
        # Calculate totals
        total_cdf_amount = sponsorship_breakdown['cdf']['total_amount'] + \
                          sponsorship_breakdown['mp']['total_amount'] + \
                          sponsorship_breakdown['other']['total_amount']
        
        total_sponsorship_amount = sponsorship_breakdown['mp']['total_sponsorship'] + \
                                  sponsorship_breakdown['other']['total_sponsorship']
        
        total_allocation = total_cdf_amount + total_sponsorship_amount
        
        # Add sponsorship statistics to response
        stats['sponsorship_breakdown'] = sponsorship_breakdown
        stats['total_cdf_amount'] = total_cdf_amount
        stats['total_sponsorship_amount'] = total_sponsorship_amount
        stats['total_allocation'] = total_allocation
        
        # Add MP sponsor names summary
        mp_sponsors = Student.objects.filter(
            sponsorship_source='mp',
            sponsor_name__isnull=False
        ).exclude(sponsor_name='').values('sponsor_name').annotate(
            count=models.Count('id'),
            total_amount=models.Sum('amount'),
            total_sponsorship=models.Sum('sponsorship_amount')
        )
        
        stats['mp_sponsors'] = list(mp_sponsors)
        
        # Add SMS statistics by sponsorship source
        sms_by_sponsorship = {
            'cdf': {
                'sent': Student.objects.filter(sponsorship_source='cdf', sms_status='sent').count(),
                'failed': Student.objects.filter(sponsorship_source='cdf', sms_status='failed').count(),
                'not_sent': Student.objects.filter(sponsorship_source='cdf', sms_status='not_sent').count(),
                'partial': Student.objects.filter(sponsorship_source='cdf', sms_status='partial').count(),
            },
            'mp': {
                'sent': Student.objects.filter(sponsorship_source='mp', sms_status='sent').count(),
                'failed': Student.objects.filter(sponsorship_source='mp', sms_status='failed').count(),
                'not_sent': Student.objects.filter(sponsorship_source='mp', sms_status='not_sent').count(),
                'partial': Student.objects.filter(sponsorship_source='mp', sms_status='partial').count(),
            },
            'other': {
                'sent': Student.objects.filter(sponsorship_source='other', sms_status='sent').count(),
                'failed': Student.objects.filter(sponsorship_source='other', sms_status='failed').count(),
                'not_sent': Student.objects.filter(sponsorship_source='other', sms_status='not_sent').count(),
                'partial': Student.objects.filter(sponsorship_source='other', sms_status='partial').count(),
            }
        }
        
        stats['sms_by_sponsorship'] = sms_by_sponsorship
        
        return Response(stats)