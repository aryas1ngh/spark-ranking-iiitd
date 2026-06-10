from rest_framework import serializers
from .models import Institution, Department, Faculty, Conference, Publication, Authorship

class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = '__all__'

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = '__all__'

class ConferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conference
        fields = '__all__'

class PublicationSerializer(serializers.ModelSerializer):
    conference = ConferenceSerializer(read_only=True)
    authors = serializers.SerializerMethodField()
    
    class Meta:
        model = Publication
        fields = ('id', 'title', 'year', 'conference', 'authors', 'doi', 'dblp_key')

    def get_authors(self, obj):
        return [a.faculty_id for a in obj.authorships.all()]

class AuthorshipSerializer(serializers.ModelSerializer):
    publication_id = serializers.IntegerField(source='publication.id', read_only=True)
    author_id = serializers.IntegerField(source='faculty.id', read_only=True)
    
    class Meta:
        model = Authorship
        fields = ('id', 'publication_id', 'author_id', 'credit')

class FacultySerializer(serializers.ModelSerializer):
    institution = InstitutionSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    authorships = AuthorshipSerializer(many=True, read_only=True)
    score = serializers.SerializerMethodField()
    
    class Meta:
        model = Faculty
        fields = '__all__'

    def get_score(self, obj):
        return round(getattr(obj, 'score', 0.0), 4)

class FacultyRankingSerializer(serializers.Serializer):
    id = serializers.IntegerField(source='faculty_id')
    name = serializers.CharField(source='faculty_name')
    score = serializers.FloatField(source='faculty_score')

class RankingSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    institution = InstitutionSerializer()
    score = serializers.FloatField()
    top_faculty = FacultyRankingSerializer(many=True)
