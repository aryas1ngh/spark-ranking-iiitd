from django.db import models

class Institution(models.Model):
    name = models.CharField(max_length=255)
    state = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name

class Department(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.name} - {self.institution.name}"

class Faculty(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='faculty')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='faculty')
    name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255, blank=True, null=True)
    orcid = models.CharField(max_length=100, blank=True, null=True)
    dblp_pid = models.CharField(max_length=100, blank=True, null=True)
    irins_id = models.CharField(max_length=100, blank=True, null=True)
    homepage = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name

class Conference(models.Model):
    acronym = models.CharField(max_length=50)
    full_name = models.CharField(max_length=500)
    dblp_key = models.CharField(max_length=100, blank=True, null=True)
    core_rank = models.CharField(max_length=10) # A*, A, Journal
    area = models.CharField(max_length=100, blank=True, null=True) # FoR code

    def __str__(self):
        return self.acronym

class Publication(models.Model):
    title = models.TextField()
    year = models.IntegerField()
    doi = models.CharField(max_length=255, blank=True, null=True)
    dblp_key = models.CharField(max_length=255, blank=True, null=True)
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='publications')

    def __str__(self):
        return self.title

class Authorship(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='authorships')
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='authorships')
    credit = models.FloatField(default=1.0) # Adjusted count (e.g., 1 / num_authors)

    class Meta:
        unique_together = ('faculty', 'publication')

    def __str__(self):
        return f"{self.faculty.name} - {self.publication.title[:30]}"
