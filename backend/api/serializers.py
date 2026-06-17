from rest_framework import serializers
from .models import Institution, Department, Faculty, Conference, Publication, Authorship


# ── Lightweight / Nested Serializers ────────────────────────

class InstitutionMiniSerializer(serializers.ModelSerializer):
    """Minimal institution representation used in nested contexts."""
    class Meta:
        model = Institution
        fields = ('id', 'name')


class ConferenceMiniSerializer(serializers.ModelSerializer):
    """Minimal conference representation for publication listings."""
    class Meta:
        model = Conference
        fields = ('acronym', 'core_rank')


class FacultyMiniSerializer(serializers.Serializer):
    """Lightweight faculty used in ranking top_faculty lists."""
    id = serializers.IntegerField()
    name = serializers.CharField()
    score = serializers.FloatField()


# ── Endpoint 1: /api/stats/ ────────────────────────────────

class StatsSerializer(serializers.Serializer):
    institutions = serializers.IntegerField()
    faculty = serializers.IntegerField()
    publications = serializers.IntegerField()
    # Fallback keys the frontend also checks
    institution_count = serializers.IntegerField(source='institutions')
    faculty_count = serializers.IntegerField(source='faculty')
    publication_count = serializers.IntegerField(source='publications')


# ── Endpoint 2: /api/areas/ ────────────────────────────────

class AreaSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()


# ── Endpoint 3: /api/rankings/ ─────────────────────────────

class RankingResultSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    institution = InstitutionMiniSerializer()
    score = serializers.FloatField()
    top_faculty = FacultyMiniSerializer(many=True)


# ── Endpoint 4: /api/institutions/{id}/ ────────────────────

class InstitutionProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    website = serializers.URLField(allow_null=True)
    summary = serializers.CharField(allow_null=True, default=None)
    rank = serializers.IntegerField()
    score = serializers.FloatField()
    area_breakdown = serializers.DictField()
    top_faculty = FacultyMiniSerializer(many=True)


# ── Endpoint 5: /api/institutions/{id}/trends/ ─────────────

class InstitutionTrendSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    score = serializers.FloatField()


# ── Endpoint 6: /api/publications/ ─────────────────────────

class PublicationResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    year = serializers.IntegerField()
    conference = ConferenceMiniSerializer()
    core_rank = serializers.CharField()
    area = serializers.CharField(allow_null=True)


# ── Endpoint 7: /api/institutions/?search= ─────────────────

class InstitutionSearchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    score = serializers.FloatField()


# ── Endpoint 8: /api/faculty/{id}/ ─────────────────────────

class AuthorshipNestedSerializer(serializers.Serializer):
    """Authorship with nested publication detail (Django through-model format)."""
    id = serializers.IntegerField()
    publication = serializers.SerializerMethodField()

    def get_publication(self, obj):
        return {
            'id': obj.publication.id,
            'title': obj.publication.title,
            'year': obj.publication.year,
            'venue': obj.publication.conference.acronym,
            'core_rank': obj.publication.conference.core_rank,
        }


class FacultyPublicationSerializer(serializers.Serializer):
    """Publication as shown inside a faculty profile."""
    title = serializers.CharField()
    year = serializers.IntegerField()
    conference = ConferenceMiniSerializer()
    core_rank = serializers.CharField()


class FacultyProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    bio = serializers.CharField(allow_null=True, default=None)
    institution = InstitutionMiniSerializer()
    areas = serializers.ListField(child=serializers.CharField())
    dblp_url = serializers.CharField(allow_null=True)
    scholar_url = serializers.CharField(allow_null=True, default=None)
    score = serializers.FloatField()
    a_star_score = serializers.FloatField()
    a_score = serializers.FloatField()
    authorships = AuthorshipNestedSerializer(many=True)


# ── Endpoint 8b: /api/faculty/ (leaderboard) ──────────────

class FacultyLeaderboardSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    institution = InstitutionMiniSerializer()
    department = serializers.CharField(allow_null=True)
    authorships = serializers.ListField(child=serializers.IntegerField())
    score = serializers.FloatField()
    name = serializers.CharField()
    designation = serializers.CharField(allow_null=True)
    orcid = serializers.CharField(allow_null=True)
    dblp_pid = serializers.CharField(allow_null=True)
    irins_id = serializers.CharField(allow_null=True)
    homepage = serializers.CharField(allow_null=True)
    institution_rank = serializers.IntegerField(allow_null=True, default=None)


# ── Endpoint 9: /api/conferences/ ──────────────────────────

class ConferenceListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='full_name')

    class Meta:
        model = Conference
        fields = ('acronym', 'name', 'core_rank', 'area')
