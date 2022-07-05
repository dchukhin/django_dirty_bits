from django.apps import apps
from django.db.models import ManyToManyField
from django.db.models.signals import post_init, post_save
from threading import Lock

hash_fnc = hash

REGISTRY_LOCK = Lock()

REGISTRY = set()
NEW_MODEL_HASH = None


def register_all(strict=False):
    models = apps.get_models()
    for model in models:
        register(model, strict)


def register(cls, strict=False):
    with REGISTRY_LOCK:
        if cls in REGISTRY:
            return

        cls.__strict_dirty_checking = strict
        REGISTRY.add(cls)

    def _init_hash(sender, instance):
        if sender in REGISTRY:
            instance.__dirty_hash, old_values = cls._get_hash(
                instance
            )
            if instance.__strict_dirty_checking:
                # Only store the old data if in strict mode
                instance.__old_values = old_values
        else:
            instance.__dirty_hash, instance.__old_values = NEW_MODEL_HASH, None

    def _convert_value(field, instance):
        # Ignoring many to many since django calls save
        # Trying to track this relationship causes performance issues
        if isinstance(field, ManyToManyField):
            return None
        else:
            return field.value_to_string(instance)

    def _get_hash(instance):
        model_key_values = tuple(
            (
                (field.name, _convert_value(field, instance)) for field in
                (instance._meta.fields + instance._meta.many_to_many)
            )
        )
        if not instance.pk:
            return NEW_MODEL_HASH, None

        return hash_fnc(model_key_values), model_key_values

    def is_dirty(self):
        if self.__dirty_hash == NEW_MODEL_HASH:
            # initial state of a model is dirty
            return True
        new_hash, new_values = cls._get_hash(self)

        if not self.__strict_dirty_checking:
            return new_hash != self.__dirty_hash
        else:
            # if the hashes are equal and the tuples are equal then its not dirty
            return new_hash != self.__dirty_hash or self.__old_values != new_values

    cls._init_hash = _init_hash
    cls._get_hash = _get_hash
    cls.is_dirty = is_dirty

    def _post_init(sender, instance, **kwargs):
        _init_hash(sender, instance)

    def _post_save(sender, instance, **kwargs):
        _init_hash(sender, instance)

    post_save.connect(_post_save, sender=cls, weak=False)
    post_init.connect(_post_init, sender=cls, weak=False)
