from django.db.models import Manager, Model, get_models
from django.db.models.signals import post_init
from threading import Lock

REGISTRY_LOCK = Lock()

REGISTRY = set()
NEW_MODEL_HASH = None


def register_all():
    models = get_models()
    for model in models:
        register(model)


def register(cls):
    with REGISTRY_LOCK:
        if cls in REGISTRY:
            return
        REGISTRY.add(cls)

    def _init_hash(sender, instance):
        if sender in REGISTRY:
            instance.__dirty_hash = cls._get_hash(instance)
        else:
            instance.__dirty_hash = NEW_MODEL_HASH

    def convert_value(value):
        """
        Must convert the complex objects to a hashable object.
        """
        if isinstance(value, Manager):
            return tuple(value.all().values_list('pk'))
        elif isinstance(value, Model):
            return value.pk
        else:
            return value

    def _get_hash(instance):
        if not instance.pk:
            return NEW_MODEL_HASH
        model_key_values = tuple(
            (
                (field_name, convert_value(getattr(instance, field_name))) for field_name in
                instance._meta.get_all_field_names()
            )
        )
        return hash(model_key_values)

    def is_dirty(self):
        if self.__dirty_hash == NEW_MODEL_HASH:
            # initial state of a model is dirty
            return True
        return cls._get_hash(self) != self.__dirty_hash

    cls._init_hash = _init_hash
    cls._get_hash = _get_hash
    cls.is_dirty = is_dirty

    def _post_init(sender, instance, **kwargs):
        _init_hash(sender, instance)

    post_init.connect(_post_init, sender=cls, weak=False)
