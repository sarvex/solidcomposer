from django import forms

from main.models import *
from workshop.models import *
from workshop import design

class NewProjectForm(forms.Form):
    title = forms.CharField(max_length=100,
        error_messages={'required': design.this_field_is_required})
    file_source = forms.FileField(error_messages={
        'required': design.this_field_is_required})
    file_mp3 = forms.FileField(error_messages={
        'required': design.this_field_is_required})
    comments = forms.CharField(max_length=1000, required=False,
        widget=forms.Textarea)

    def clean_file_mp3(self):
        filename = self.cleaned_data['file_mp3']

        if filename.name[-3:].lower() != 'mp3':
            raise forms.ValidationError(design.uploaded_file_must_be_mp3)

        return filename

class NewBandForm(forms.Form):
    band_name = forms.CharField(max_length=100,
        error_messages={'required': design.this_field_is_required})

    def clean_band_name(self):
        band_name = self.cleaned_data['band_name']
        disallowed_chars = Band.disallowed_chars
        for c in band_name:
            if c in disallowed_chars:
                raise forms.ValidationError(design.cannot_use_x_in_band_name % disallowed_chars)
        return band_name

class BandSettingsForm(forms.Form):
    pass