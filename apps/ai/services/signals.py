"""Cache invalidation for :mod:`apps.ai.services.cache`.

- ``WebSiteConfig`` is a global singleton feeding every company -> drop all.
- ``Service`` / ``Company`` writes -> drop only their company.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.ai.services import cache as deps_cache
from apps.core.models import Company, Service, WebSiteConfig


@receiver([post_save, post_delete], sender=WebSiteConfig)
def _website_config_changed(sender, instance, **kwargs):
    deps_cache.invalidate_all()


@receiver([post_save, post_delete], sender=Service)
def _service_changed(sender, instance, **kwargs):
    deps_cache.invalidate_company(instance.company_id)


@receiver([post_save, post_delete], sender=Company)
def _company_changed(sender, instance, **kwargs):
    deps_cache.invalidate_company(instance.id)
