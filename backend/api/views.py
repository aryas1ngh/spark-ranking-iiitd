import math

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from django.db.models import Sum, F, Case, When, Value, FloatField, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404

from .models import Institution, Faculty, Conference, Publication, Authorship
from .serializers import (
    StatsSerializer, AreaSerializer, RankingResultSerializer,
    InstitutionProfileSerializer, InstitutionTrendSerializer,
    PublicationResultSerializer, InstitutionSearchSerializer,
    FacultyProfileSerializer, FacultyLeaderboardSerializer,
    ConferenceListSerializer, FacultyPublicationSerializer,
    AuthorshipNestedSerializer, InstitutionMiniSerializer,
)

# FoR code → human-readable name mapping
FOR_DESCRIPTIONS = {
    '4601': 'Applied Computing',
    '4602': 'Artificial Intelligence',
    '4603': 'Computer Vision & Multimedia',
    '4604': 'Cybersecurity and Privacy',
    '4605': 'Data Management and Data Science',
    '4606': 'Distributed Computing',
    '4607': 'Graphics, Augmented Reality and Games',
    '4608': 'Human-Centred Computing',
    '4609': 'Information Systems',
    '4610': 'Library and Information Studies',
    '4611': 'Machine Learning',
    '4612': 'Software Engineering',
    '4613': 'Theory of Computation',
}

# Weighted scoring: A*=4.0, A=2.0, else=1.0
SCORE_WEIGHT_EXPR = Case(
    When(publication__conference__core_rank='A*', then=Value(4.0)),
    When(publication__conference__core_rank='A', then=Value(2.0)),
    default=Value(1.0),
    output_field=FloatField(),
)


def _parse_int_param(params, name, min_val=None, max_val=None):
    """Parse a query param as an int, or raise a DRF ValidationError (HTTP 400).

    Returns None when the param is absent/empty. Raising (rather than casting
    inline with int()) is what turns malformed input — 'abc', "2020'", '2015.5',
    an out-of-range year — into a clean 400 JSON body instead of an unhandled
    ValueError, which under DEBUG surfaced as a 500 debug page. DRF's exception
    handler renders the raised error automatically, so callers need no changes.
    """
    raw = params.get(name)
    if raw is None or raw == '':
        return None
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: "Must be a valid integer."})
    if min_val is not None and val < min_val:
        raise ValidationError({name: f"Must be greater than or equal to {min_val}."})
    if max_val is not None and val > max_val:
        raise ValidationError({name: f"Must be less than or equal to {max_val}."})
    return val


def _build_authorship_filters(params):
    """Build Q filters for authorships from query params."""
    # Start by excluding workshop papers globally from all authorship calculations
    filters = Q(publication__is_workshop=False)

    start_year = _parse_int_param(params, 'start_year', min_val=1900, max_val=2100)
    end_year = _parse_int_param(params, 'end_year', min_val=1900, max_val=2100)
    area = params.get('area')

    if start_year is not None:
        filters &= Q(publication__year__gte=start_year)
    if end_year is not None:
        filters &= Q(publication__year__lte=end_year)
    if area:
        areas = [a.strip() for a in area.split(',')]
        filters &= Q(publication__conference__area__in=areas)
    return filters


def _compute_faculty_score(faculty_id, extra_filters=Q()):
    """Compute weighted score for a single faculty member."""
    return Authorship.objects.filter(
        faculty_id=faculty_id
    ).filter(extra_filters).annotate(
        weighted=F('credit') * Case(
            When(publication__conference__core_rank='A*', then=Value(4.0)),
            When(publication__conference__core_rank='A', then=Value(2.0)),
            default=Value(1.0),
            output_field=FloatField(),
        )
    ).aggregate(total=Coalesce(Sum('weighted'), Value(0.0)))['total']


def _geo_mean(values):
    """Compute geometric mean of a list of positive values.
    
    Uses log-sum-exp for numerical stability.
    Returns 0.0 if no positive values.
    """
    positive = [v for v in values if v > 0]
    if not positive:
        return 0.0
    return math.exp(sum(math.log(v) for v in positive) / len(positive))


def _compute_institution_geo_mean(authorships_qs):
    """Compute institution score as geometric mean of per-area weighted scores.
    
    Groups publications by their conference's area (FoR code),
    sums weighted scores per area, then returns the geometric mean
    across all areas.
    
    Also returns area_scores dict for breakdown display.
    """
    area_scores = {}  # area_code -> total weighted score
    for a in authorships_qs:
        area = a.publication.conference.area or 'other'
        area_scores[area] = area_scores.get(area, 0.0) + a.weighted

    geo_score = _geo_mean(list(area_scores.values()))
    return geo_score, area_scores


def _compute_all_institution_geo_means():
    """Compute geo-mean scores for ALL institutions at once.
    
    Returns dict: {institution_id: geo_mean_score}
    Used for computing institution ranks across the system.
    """
    auths = Authorship.objects.filter(
        publication__is_workshop=False
    ).select_related(
        'faculty__institution', 'publication__conference'
    ).annotate(
        weighted=F('credit') * Case(
            When(publication__conference__core_rank='A*', then=Value(4.0)),
            When(publication__conference__core_rank='A', then=Value(2.0)),
            default=Value(1.0),
            output_field=FloatField(),
        )
    )

    # inst_id -> {area -> score}
    inst_area_scores = {}
    for a in auths:
        iid = a.faculty.institution_id
        area = a.publication.conference.area or 'other'
        if iid not in inst_area_scores:
            inst_area_scores[iid] = {}
        inst_area_scores[iid][area] = inst_area_scores[iid].get(area, 0.0) + a.weighted

    return {iid: _geo_mean(list(areas.values())) for iid, areas in inst_area_scores.items()}


# ── 1. GET /api/stats/ ─────────────────────────────────────

class StatsView(APIView):
    def get(self, request):
        data = {
            'institutions': Institution.objects.count(),
            'faculty': Faculty.objects.count(),
            'publications': Publication.objects.count(),
        }
        serializer = StatsSerializer(data)
        return Response(serializer.data)


# ── 2. GET /api/areas/ ─────────────────────────────────────

class AreasView(APIView):
    def get(self, request):
        # Get distinct area codes from conferences
        area_codes = Conference.objects.exclude(
            area__isnull=True
        ).exclude(
            area=''
        ).values_list('area', flat=True).distinct().order_by('area')

        areas = []
        for code in area_codes:
            name = FOR_DESCRIPTIONS.get(code, code)
            area_id = name.lower().replace(' ', '_').replace('&', 'and').replace(',', '')
            areas.append({'id': area_id, 'code': code, 'name': name})

        serializer = AreaSerializer(areas, many=True)
        return Response(serializer.data)


# ── 3. GET /api/rankings/ ──────────────────────────────────

class RankingsView(APIView):
    def get(self, request):
        filters = _build_authorship_filters(request.query_params)

        # Get all authorships matching filters, annotate with weight
        authorships = Authorship.objects.filter(filters).select_related(
            'faculty', 'faculty__institution', 'publication__conference'
        ).annotate(
            weighted=F('credit') * Case(
                When(publication__conference__core_rank='A*', then=Value(4.0)),
                When(publication__conference__core_rank='A', then=Value(2.0)),
                default=Value(1.0),
                output_field=FloatField(),
            )
        )

        # Accumulate per-area scores per institution, and per-faculty scores
        inst_map = {}  # inst_id -> { inst, area_scores, faculty }
        for a in authorships:
            inst = a.faculty.institution
            if inst.id not in inst_map:
                inst_map[inst.id] = {
                    'institution': {'id': inst.id, 'name': inst.name},
                    'area_scores': {},
                    'faculty': {},
                }
            entry = inst_map[inst.id]

            # Accumulate per-area score
            area = a.publication.conference.area or 'other'
            entry['area_scores'][area] = entry['area_scores'].get(area, 0.0) + a.weighted

            fac = a.faculty
            if fac.id not in entry['faculty']:
                entry['faculty'][fac.id] = {'id': fac.id, 'name': fac.name, 'score': 0.0}
            entry['faculty'][fac.id]['score'] += a.weighted

        # Compute geometric mean score for each institution
        for entry in inst_map.values():
            entry['score'] = _geo_mean(list(entry['area_scores'].values()))

        # Sort and rank
        ranked = sorted(inst_map.values(), key=lambda x: x['score'], reverse=True)
        results = []
        for idx, item in enumerate(ranked):
            top_fac = sorted(item['faculty'].values(), key=lambda f: f['score'], reverse=True)[:5]
            for f in top_fac:
                f['score'] = round(f['score'], 2)
            results.append({
                'rank': idx + 1,
                'institution': item['institution'],
                'score': round(item['score'], 2),
                'top_faculty': top_fac,
            })

        serializer = RankingResultSerializer(results, many=True)
        return Response({'results': serializer.data})


# ── 4. GET /api/institutions/{id}/ ─────────────────────────

class InstitutionDetailView(APIView):
    def get(self, request, pk):
        inst = get_object_or_404(Institution, pk=pk)

        # Compute total score + area breakdown
        authorships = Authorship.objects.filter(
            faculty__institution=inst,
            publication__is_workshop=False
        ).select_related('publication__conference', 'faculty').annotate(
            weighted=F('credit') * Case(
                When(publication__conference__core_rank='A*', then=Value(4.0)),
                When(publication__conference__core_rank='A', then=Value(2.0)),
                default=Value(1.0),
                output_field=FloatField(),
            )
        )

        geo_score, area_scores = _compute_institution_geo_mean(authorships)
        faculty_scores = {}

        for a in authorships:
            fac = a.faculty
            if fac.id not in faculty_scores:
                faculty_scores[fac.id] = {'id': fac.id, 'name': fac.name, 'score': 0.0}
            faculty_scores[fac.id]['score'] += a.weighted

        # Round area scores
        area_breakdown = {k: round(v, 2) for k, v in area_scores.items()}

        # Top faculty
        top_fac = sorted(faculty_scores.values(), key=lambda f: f['score'], reverse=True)[:10]
        for f in top_fac:
            f['score'] = round(f['score'], 2)

        # Compute rank (position among all institutions) using geo mean
        all_inst_geo = _compute_all_institution_geo_means()

        sorted_insts = sorted(all_inst_geo.items(), key=lambda x: x[1], reverse=True)
        rank = next((i + 1 for i, (iid, _) in enumerate(sorted_insts) if iid == inst.id), None)

        data = {
            'id': inst.id,
            'name': inst.name,
            'website': inst.website,
            'summary': None,
            'rank': rank or 0,
            'score': round(geo_score, 2),
            'area_breakdown': area_breakdown,
            'top_faculty': top_fac,
        }

        serializer = InstitutionProfileSerializer(data)
        return Response(serializer.data)


# ── 5. GET /api/institutions/{id}/trends/ ──────────────────

class InstitutionTrendsView(APIView):
    def get(self, request, pk):
        get_object_or_404(Institution, pk=pk)

        year_scores = Authorship.objects.filter(
            faculty__institution_id=pk,
            publication__is_workshop=False
        ).values('publication__year').annotate(
            score=Sum(F('credit') * Case(
                When(publication__conference__core_rank='A*', then=Value(4.0)),
                When(publication__conference__core_rank='A', then=Value(2.0)),
                default=Value(1.0),
                output_field=FloatField(),
            ))
        ).order_by('publication__year')

        data = [{'year': row['publication__year'], 'score': round(row['score'], 2)} for row in year_scores]
        serializer = InstitutionTrendSerializer(data, many=True)
        return Response(serializer.data)


# ── 6. GET /api/publications/ ──────────────────────────────

class PublicationsView(APIView):
    def get(self, request):
        qs = Publication.objects.select_related('conference').filter(is_workshop=False)

        institution_id = _parse_int_param(request.query_params, 'institution', min_val=1)
        if institution_id is not None:
            qs = qs.filter(authorships__faculty__institution_id=institution_id).distinct()

        pubs = []
        for pub in qs.order_by('-year')[:500]:
            pubs.append({
                'id': pub.id,
                'title': pub.title,
                'year': pub.year,
                'conference': pub.conference,
                'core_rank': pub.conference.core_rank,
                'area': pub.conference.area,
            })

        serializer = PublicationResultSerializer(pubs, many=True)
        return Response({'results': serializer.data})


# ── 7. GET /api/institutions/?search= ──────────────────────

class InstitutionSearchView(APIView):
    def get(self, request):
        search = request.query_params.get('search', '')
        qs = Institution.objects.all()
        if search:
            qs = qs.filter(name__icontains=search)

        # Compute scores for each matching institution
        inst_scores = Authorship.objects.filter(
            faculty__institution__in=qs,
            publication__is_workshop=False
        ).values('faculty__institution_id').annotate(
            total=Sum(F('credit') * Case(
                When(publication__conference__core_rank='A*', then=Value(4.0)),
                When(publication__conference__core_rank='A', then=Value(2.0)),
                default=Value(1.0),
                output_field=FloatField(),
            ))
        )
        score_map = {row['faculty__institution_id']: row['total'] for row in inst_scores}

        results = []
        for inst in qs:
            results.append({
                'id': inst.id,
                'name': inst.name,
                'score': round(score_map.get(inst.id, 0.0), 2),
            })

        results.sort(key=lambda x: x['score'], reverse=True)
        serializer = InstitutionSearchSerializer(results, many=True)
        return Response(serializer.data)


# ── 8. GET /api/faculty/{id}/ ──────────────────────────────

class FacultyDetailView(APIView):
    def get(self, request, pk):
        fac = get_object_or_404(Faculty, pk=pk)

        authorships = Authorship.objects.filter(
            faculty=fac,
            publication__is_workshop=False
        ).select_related('publication', 'publication__conference')

        total_score = 0.0
        a_star_score = 0.0
        a_score = 0.0
        pubs = []
        authorship_data = []
        areas_set = set()

        for a in authorships:
            conf = a.publication.conference
            weight = 4.0 if conf.core_rank == 'A*' else (2.0 if conf.core_rank == 'A' else 1.0)
            weighted = a.credit * weight
            total_score += weighted
            if conf.core_rank == 'A*':
                a_star_score += weighted
            elif conf.core_rank == 'A':
                a_score += weighted

            if conf.area:
                areas_set.add(conf.area)

            pubs.append({
                'title': a.publication.title,
                'year': a.publication.year,
                'conference': conf,
                'core_rank': conf.core_rank,
            })
            # Also remove `pubs` from the response payload
            authorship_data.append(a)

        pubs.sort(key=lambda p: p['year'], reverse=True)

        dblp_url = f"https://dblp.org/pid/{fac.dblp_pid}" if fac.dblp_pid else None

        data = {
            'id': fac.id,
            'name': fac.name,
            'bio': fac.designation,
            'institution': fac.institution,
            'areas': sorted(areas_set),
            'dblp_url': dblp_url,
            'scholar_url': None,
            'score': round(total_score, 2),
            'a_star_score': round(a_star_score, 2),
            'a_score': round(a_score, 2),
            'authorships': authorship_data,
        }

        serializer = FacultyProfileSerializer(data)
        return Response(serializer.data)


# ── 8b. GET /api/faculty/ (leaderboard) ───────────────────

class FacultyListView(APIView):
    def get(self, request):
        filters = _build_authorship_filters(request.query_params)
        search = request.query_params.get('search', '')

        # Start with all faculty (optionally filtered by name)
        fac_qs = Faculty.objects.select_related('institution', 'department').all()
        if search:
            fac_qs = fac_qs.filter(name__icontains=search)

        # Initialize map with all matching faculty
        fac_map = {}
        for f in fac_qs:
            fac_map[f.id] = {
                'id': f.id,
                'name': f.name,
                'score': 0.0,
                'institution': f.institution,
                'institution_rank': None,
                'department': f.department.name if f.department else None,
                'designation': f.designation,
                'orcid': f.orcid,
                'dblp_pid': f.dblp_pid,
                'irins_id': f.irins_id,
                'homepage': f.homepage,
                'authorships': [],
            }

        # Get authorships with filters
        auths = Authorship.objects.filter(filters).select_related(
            'faculty', 'faculty__institution'
        ).annotate(
            weighted=F('credit') * Case(
                When(publication__conference__core_rank='A*', then=Value(4.0)),
                When(publication__conference__core_rank='A', then=Value(2.0)),
                default=Value(1.0),
                output_field=FloatField(),
            )
        )

        # Accumulate scores per faculty
        for a in auths:
            fid = a.faculty.id
            if fid in fac_map:
                fac_map[fid]['score'] += a.weighted
                fac_map[fid]['authorships'].append(a.id)

        # Compute institution ranks using geometric mean of per-area scores
        all_inst_geo = _compute_all_institution_geo_means()
        sorted_insts = sorted(all_inst_geo.items(), key=lambda x: x[1], reverse=True)
        inst_rank_map = {iid: idx + 1 for idx, (iid, _) in enumerate(sorted_insts)}

        # Build result
        results = []
        for f in fac_map.values():
            f['score'] = round(f['score'], 2)
            f['institution_rank'] = inst_rank_map.get(f['institution'].id)
            results.append(f)

        results.sort(key=lambda x: x['score'], reverse=True)
        serializer = FacultyLeaderboardSerializer(results, many=True)
        return Response(serializer.data)


# ── 9. GET /api/conferences/ ──────────────────────────────

class ConferencesView(APIView):
    def get(self, request):
        confs = Conference.objects.all().order_by('core_rank', 'acronym')
        serializer = ConferenceListSerializer(confs, many=True)
        return Response(serializer.data)
