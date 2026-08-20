from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAdminUser
from .models import APILog
from .serializers import APILogSerializer


class APILogListView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = APILogSerializer
    queryset = APILog.objects.all().order_by('-checked_at')