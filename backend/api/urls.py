from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
from .views import (
    StatsView, AreasView, RankingsView,
    InstitutionSearchView, InstitutionDetailView, InstitutionTrendsView,
    PublicationsView,
    FacultyListView, FacultyDetailView,
    ConferencesView,
)


@api_view(['GET'])
def api_root(request):
    return Response({
        'stats': reverse('stats', request=request),
        'areas': reverse('areas', request=request),
        'rankings': reverse('rankings', request=request),
        'institutions': reverse('institution-search', request=request),
        'publications': reverse('publications', request=request),
        'faculty': reverse('faculty-list', request=request),
        'conferences': reverse('conferences', request=request),
    })

urlpatterns = [
    # API root — lists all endpoints
    path('', api_root, name='api-root'),

    # 1. General stats
    path('stats/', StatsView.as_view(), name='stats'),

    # 2. Research areas
    path('areas/', AreasView.as_view(), name='areas'),

    # 3. Institution rankings (filtered)
    path('rankings/', RankingsView.as_view(), name='rankings'),

    # 7. Institution search (typeahead) — must come before {id} pattern
    path('institutions/', InstitutionSearchView.as_view(), name='institution-search'),

    # 4. Institution profile
    path('institutions/<int:pk>/', InstitutionDetailView.as_view(), name='institution-detail'),

    # 5. Institution score trends
    path('institutions/<int:pk>/trends/', InstitutionTrendsView.as_view(), name='institution-trends'),

    # 6. Publications listing
    path('publications/', PublicationsView.as_view(), name='publications'),

    # 8b. Faculty leaderboard & search — must come before {id} pattern
    path('faculty/', FacultyListView.as_view(), name='faculty-list'),

    # 8. Faculty profile
    path('faculty/<int:pk>/', FacultyDetailView.as_view(), name='faculty-detail'),

    # 9. Conferences listing
    path('conferences/', ConferencesView.as_view(), name='conferences'),
]
