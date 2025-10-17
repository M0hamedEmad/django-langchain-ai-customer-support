from __future__ import annotations

from rest_framework import serializers

from apps.core.models import Booking, Service


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "description", "price", "duration_minutes", "is_active"]


class BookingSerializer(serializers.ModelSerializer):
    service = ServiceSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "status",
            "date",
            "service_text",
            "notes",
            "source",
            "service",
        ]


class FAQUpsertItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    question = serializers.CharField(max_length=10000)
    answer = serializers.CharField(max_length=20000)
    informal_answer = serializers.CharField(
        max_length=20000, required=False, allow_blank=True
    )
    category = serializers.CharField(max_length=255, required=False, allow_blank=True)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=128), required=False
    )
    example_dialogue = serializers.CharField(
        max_length=20000, required=False, allow_blank=True
    )
    rag_tips = serializers.CharField(max_length=20000, required=False, allow_blank=True)
