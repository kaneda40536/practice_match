from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from accounts.views import BoardRequiredMixin
from .forms import FacilityForm
from .models import Facility


class FacilityListView(BoardRequiredMixin, ListView):
    template_name = "facilities/facility_list.html"
    context_object_name = "facilities"

    def get_queryset(self):
        return Facility.objects.prefetch_related("sports").order_by("name")


class FacilityCreateView(BoardRequiredMixin, CreateView):
    model = Facility
    form_class = FacilityForm
    template_name = "facilities/facility_form.html"
    success_url = reverse_lazy("facility_list")

    def form_valid(self, form):
        messages.success(self.request, "施設を登録しました。")
        return super().form_valid(form)


class FacilityUpdateView(BoardRequiredMixin, UpdateView):
    model = Facility
    form_class = FacilityForm
    template_name = "facilities/facility_form.html"
    success_url = reverse_lazy("facility_list")

    def form_valid(self, form):
        messages.success(self.request, "施設情報を更新しました。")
        return super().form_valid(form)


class FacilityDeleteView(BoardRequiredMixin, DeleteView):
    model = Facility
    template_name = "facilities/facility_confirm_delete.html"
    success_url = reverse_lazy("facility_list")

    def form_valid(self, form):
        name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f"「{name}」を削除しました。")
        return response