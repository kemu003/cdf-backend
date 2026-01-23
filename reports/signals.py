# reports/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Report, ReportLog

@receiver(pre_save, sender=Report)
def store_old_status(sender, instance, **kwargs):
    """Store the old status before saving"""
    if instance.pk:  # Only for existing instances
        try:
            old_instance = Report.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Report.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

@receiver(post_save, sender=Report)
def create_report_log(sender, instance, created, **kwargs):
    """Create log entry when report is saved"""
    if created:
        ReportLog.objects.create(
            report=instance,
            level='info',
            message=f"Report '{instance.title}' created by {instance.generated_by}",
            details={'action': 'create', 'user': instance.generated_by.username}
        )
    else:
        # Check if status changed
        old_status = getattr(instance, '_old_status', None)
        if old_status is not None and instance.status != old_status:
            ReportLog.objects.create(
                report=instance,
                level='info',
                message=f"Report status changed from {old_status} to {instance.status}",
                details={'old_status': old_status, 'new_status': instance.status}
            )