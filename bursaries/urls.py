from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WardViewSet, ConstituencyBudgetViewSet, AllocationViewSet

router = DefaultRouter()
router.register(r'wards', WardViewSet)
router.register(r'budgets', ConstituencyBudgetViewSet)
router.register(r'allocations', AllocationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
