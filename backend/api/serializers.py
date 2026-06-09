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
    
    class Meta:
        model = Publication
        fields = '__all__'

class AuthorshipSerializer(serializers.ModelSerializer):
    publication = PublicationSerializer(read_only=True)
    
    class Meta:
        model = Authorship
        fields = '__all__'

class FacultySerializer(serializers.ModelSerializer):
    institution = InstitutionSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    authorships = AuthorshipSerializer(many=True, read_only=True)
    
    class Meta:
        model = Faculty
        fields = '__all__'

# For rankings, we might want a custom serializer that aggregates data
class RankingSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    institution = InstitutionSerializer()
    score = serializers.FloatField()
    papers = serializers.IntegerField()
    faculty_count = serializers.IntegerField()
