from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InstitutionViewSet, FacultyViewSet, ConferenceViewSet, PublicationViewSet, RankingViewSet

router = DefaultRouter()
router.register(r'institutions', InstitutionViewSet, basename='institution')
router.register(r'faculty', FacultyViewSet, basename='faculty')
router.register(r'conferences', ConferenceViewSet, basename='conference')
router.register(r'publications', PublicationViewSet, basename='publication')
router.register(r'rankings', RankingViewSet, basename='ranking')

urlpatterns = [
    path('', include(router.urls)),
]
