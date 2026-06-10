from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Sum, Count, F, Case, When, Value, FloatField
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import Institution, Faculty, Conference, Publication, Authorship
from .serializers import (
    InstitutionSerializer, FacultySerializer, ConferenceSerializer, 
    PublicationSerializer, RankingSerializer, AuthorshipSerializer
)

class InstitutionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Institution.objects.all()
    serializer_class = InstitutionSerializer

class FacultyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Faculty.objects.annotate(
        score=Coalesce(Sum(
            F('authorships__credit') * Case(
                When(authorships__publication__conference__core_rank='A*', then=Value(4.0)),
                When(authorships__publication__conference__core_rank='A', then=Value(2.0)),
                default=Value(1.0),
                output_field=FloatField()
            )
        ), Value(0.0))
    ).all()
    serializer_class = FacultySerializer

class ConferenceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Conference.objects.all()
    serializer_class = ConferenceSerializer

class PublicationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Publication.objects.prefetch_related('authorships').all()
    serializer_class = PublicationSerializer

class AuthorshipViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Authorship.objects.all()
    serializer_class = AuthorshipSerializer

class RankingViewSet(viewsets.ViewSet):
    def list(self, request):
        area = request.query_params.get('area')
        start_year = request.query_params.get('start_year')
        end_year = request.query_params.get('end_year')
        top_n = int(request.query_params.get('top_n', 5))

        # Filter authorships
        authorships = Authorship.objects.all()
        if start_year:
            authorships = authorships.filter(publication__year__gte=int(start_year))
        if end_year:
            authorships = authorships.filter(publication__year__lte=int(end_year))
        if area:
            areas = [a.strip() for a in area.split(',')]
            authorships = authorships.filter(publication__conference__area__in=areas)

        # Calculate weight using Case/When
        authorships = authorships.annotate(
            conf_weight=Case(
                When(publication__conference__core_rank='A*', then=Value(4.0)),
                When(publication__conference__core_rank='A', then=Value(2.0)),
                default=Value(1.0),
                output_field=FloatField()
            )
        ).annotate(
            weighted_credit=F('credit') * F('conf_weight')
        )

        # Calculate scores per faculty
        faculty_scores = {}
        for a in authorships.select_related('faculty', 'faculty__institution'):
            fac_id = a.faculty.id
            if fac_id not in faculty_scores:
                faculty_scores[fac_id] = {
                    'faculty_id': fac_id,
                    'faculty_name': a.faculty.name,
                    'institution_id': a.faculty.institution_id,
                    'faculty_score': 0.0
                }
            faculty_scores[fac_id]['faculty_score'] += a.weighted_credit

        # Group by institution
        institutions = Institution.objects.all()
        inst_data = {inst.id: {'institution': inst, 'score': 0.0, 'faculty': []} for inst in institutions}

        for fac_id, data in faculty_scores.items():
            if data['faculty_score'] > 0:
                inst_id = data['institution_id']
                inst_data[inst_id]['score'] += data['faculty_score']
                inst_data[inst_id]['faculty'].append(data)

        # Sort institutions by score and pick top N faculty
        ranked_institutions = []
        for inst_id, data in inst_data.items():
            if data['score'] > 0:
                sorted_faculty = sorted(data['faculty'], key=lambda x: x['faculty_score'], reverse=True)
                ranked_institutions.append({
                    'institution': data['institution'],
                    'score': round(data['score'], 4),
                    'top_faculty': sorted_faculty[:top_n]
                })

        ranked_institutions.sort(key=lambda x: x['score'], reverse=True)
        for idx, item in enumerate(ranked_institutions):
            item['rank'] = idx + 1
            for fac in item['top_faculty']:
                fac['faculty_score'] = round(fac['faculty_score'], 4)

        serializer = RankingSerializer(ranked_institutions, many=True)
        
        response_data = {
            "area": area,
            "start_year": int(start_year) if start_year else None,
            "end_year": int(end_year) if end_year else None,
            "generated_at": timezone.now().isoformat(),
            "institutions": serializer.data
        }
        
        return Response(response_data)
