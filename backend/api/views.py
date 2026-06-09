from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Sum, Count, F
from .models import Institution, Faculty, Conference, Publication
from .serializers import (
    InstitutionSerializer, FacultySerializer, ConferenceSerializer, 
    PublicationSerializer, RankingSerializer
)

class InstitutionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Institution.objects.all()
    serializer_class = InstitutionSerializer

class FacultyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Faculty.objects.all()
    serializer_class = FacultySerializer

class ConferenceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Conference.objects.all()
    serializer_class = ConferenceSerializer

class PublicationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Publication.objects.all()
    serializer_class = PublicationSerializer

class RankingViewSet(viewsets.ViewSet):
    def list(self, request):
        # Basic ranking logic: aggregate authorships score per institution
        institutions = Institution.objects.annotate(
            score=Sum('faculty__authorships__credit'),
            papers=Count('faculty__authorships__publication', distinct=True),
            faculty_count=Count('faculty', distinct=True)
        ).filter(score__gt=0).order_by('-score')
        
        # Build the ranked response
        ranked_data = []
        rank = 1
        for inst in institutions:
            ranked_data.append({
                'rank': rank,
                'institution': inst,
                'score': round(inst.score, 4),
                'papers': inst.papers,
                'faculty_count': inst.faculty_count
            })
            rank += 1
            
        serializer = RankingSerializer(ranked_data, many=True)
        return Response(serializer.data)
