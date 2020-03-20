from rest_framework import serializers

from ESSArch_Core.fixity.models import ConversionTool, Validation
from ESSArch_Core.fixity.validation import get_backend as get_validator
from ESSArch_Core.ip.models import InformationPackage


class ConversionToolSerializer(serializers.ModelSerializer):
    form = serializers.JSONField(read_only=True)

    class Meta:
        model = ConversionTool
        fields = ('name', 'form',)


class ValidatorWorkflowSerializer(serializers.Serializer):
    purpose = serializers.CharField(default='Validation')
    information_package = serializers.PrimaryKeyRelatedField(queryset=InformationPackage.objects.all())
    validators = serializers.ListField(min_length=1, child=serializers.JSONField())

    def validate_validators(self, validators):
        new_data = []
        ip = self.context['request'].data.get('information_package', None)
        sub_context = {'information_package': ip}
        sub_context.update(self.context)

        for validator in validators:
            name = validator.pop('name')
            klass = get_validator(name)

            serializer = klass.get_serializer_class()(
                data=validator, context=sub_context,
            )
            serializer.is_valid(True)
            data = serializer.validated_data
            data['name'] = name

            options_data = validator.pop('options', {})
            options_context = {
                'information_package': ip,
                'base_data': data,
            }
            options_serializer = klass.get_options_serializer_class()(
                data=options_data,
                context=options_context,
            )

            options_serializer.is_valid(True)
            data['options'] = options_serializer.validated_data

            new_data.append(data)

        return new_data


class ValidationSerializer(serializers.ModelSerializer):
    specification = serializers.JSONField(read_only=True)

    class Meta:
        model = Validation
        fields = ('id', 'filename', 'validator', 'passed', 'message', 'specification',
                  'information_package', 'time_started', 'time_done', 'required', 'task')


class ValidationFilesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Validation
        fields = ('id', 'filename', 'passed', 'time_started', 'time_done',)
