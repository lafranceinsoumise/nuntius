from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import (
    ValidationError,
    ImproperlyConfigured,
    ObjectDoesNotExist,
)
from django import forms
from django.forms import ChoiceField, Field
from django.utils.translation import gettext as _


class GenericModelChoiceIterator:
    def __init__(self, field):
        self.field = field
        self.querysets = field.querysets

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        querysets = [qs.all() for qs in self.querysets]

        for queryset in querysets:
            # Can't use iterator() when queryset uses prefetch_related()
            if not queryset._prefetch_related_lookups:
                queryset = queryset.iterator()
            for obj in queryset:
                yield self.choice(obj)

    def __len__(self):
        return sum([len(qs) for qs in self.querysets]) + (
            1 if self.field.empty_label is not None else 0
        )

    def choice(self, obj):
        return self.field.prepare_value(obj), self.field.label_from_instance(obj)


class GenericModelChoiceField(forms.ModelChoiceField):
    iterator = GenericModelChoiceIterator

    def __init__(
        self,
        querysets,
        empty_label=_("Send to everyone"),
        required=True,
        widget=None,
        label=None,
        initial=None,
        help_text="",
        limit_choices_to=None,
        **kwargs
    ):
        if required and (initial is not None):
            self.empty_label = None
        else:
            self.empty_label = empty_label

        # Call Field instead of ChoiceField __init__() because we don't need
        # ChoiceField.__init__().
        Field.__init__(
            self,
            required=required,
            widget=widget,
            label=label,
            initial=initial,
            help_text=help_text,
            **kwargs
        )

        self._querysets = querysets

    def __deepcopy__(self, memo):
        result = super(ChoiceField, self).__deepcopy__(memo)
        # Need to force a new ModelChoiceIterator to be created, bug #11183
        if self.querysets is not None:
            result.querysets = [qs.all() for qs in self.querysets]
        return result

    def _get_querysets(self):
        if callable(self._querysets):
            querysets = self._querysets()
        else:
            querysets = self._querysets

        if len(querysets) > len(set([qs.model for qs in querysets])):
            raise ImproperlyConfigured()

        return querysets

    def _set_querysets(self, querysets):
        self._querysets = querysets
        self.widget.choices = self.choices

    querysets = property(_get_querysets, _set_querysets)

    def get_limit_choices_to(self):
        return None

    def get_queryset_for_content_type(self, content_type_id):
        content_type = ContentType.objects.get_for_id(content_type_id)

        for queryset in self.querysets:
            if queryset.model == content_type.model_class():
                return queryset

        raise ValidationError(
            self.error_messages["invalid_choice"], code="invalid_choice"
        )

    def prepare_value(self, value):
        if hasattr(value, "_meta"):
            return "%s-%s" % (ContentType.objects.get_for_model(value).pk, value.pk)

        return value

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            ct_key = value.split("-")[0]
            object_key = value.split("-", 1)[1]
            queryset = self.get_queryset_for_content_type(ct_key)
            return queryset.get(pk=object_key)
        except (ValueError, TypeError, ObjectDoesNotExist):
            raise ValidationError(
                self.error_messages["invalid_choice"], code="invalid_choice"
            )
